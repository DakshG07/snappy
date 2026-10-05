import base64
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings
from app.services import gemini_document_service as gemini


class FakeResponse:
    def __init__(self, body: dict[str, Any], status_code: int = 200):
        self.body = body
        self.status_code = status_code
        self.request = httpx.Request("POST", "https://generativelanguage.googleapis.com/test")

    def json(self) -> dict[str, Any]:
        return self.body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            response = httpx.Response(self.status_code, request=self.request, json=self.body)
            raise httpx.HTTPStatusError("Gemini request failed", request=self.request, response=response)


def test_gemini_vision_uses_one_image_and_structured_output(monkeypatch, tmp_path) -> None:
    captured: dict[str, Any] = {}
    image = tmp_path / "scanned.jpg"
    image.write_bytes(b"processed-image-bytes")

    def fake_post(url: str, **kwargs) -> FakeResponse:
        captured.update({"url": url, **kwargs})
        return FakeResponse(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": '{"transcription":"# Momentum Lab\\n\\n| Trial | Mass |\\n|---|---|\\n| 1 | 2.0 |","title":"Momentum Lab","category":"Physics","category_confidence":0.94}'
                                }
                            ]
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(gemini.httpx, "post", fake_post)
    result = gemini.analyze_document(
        image,
        ["Physics", "English"],
        datetime.now(timezone.utc),
    )

    assert result.transcription.startswith("# Momentum Lab")
    assert "| Trial | Mass |" in result.transcription
    assert result.title == "Momentum Lab"
    assert result.category_name == "Physics"
    assert result.category_confidence == 0.94
    assert result.error is None
    assert captured["url"].endswith(f"/{settings.gemini_model}:generateContent")
    payload = captured["json"]
    assert len(payload["contents"][0]["parts"]) == 2
    inline = payload["contents"][0]["parts"][0]["inlineData"]
    assert base64.b64decode(inline["data"]) == b"processed-image-bytes"
    assert inline["mimeType"] == "image/jpeg"
    schema = payload["generationConfig"]["responseJsonSchema"]
    assert schema["properties"]["category"]["enum"] == ["Physics", "English", "Needs Review"]
    assert schema["required"] == ["transcription", "title", "category", "category_confidence"]
    instruction = payload["systemInstruction"]["parts"][0]["text"]
    assert "Do not summarize" in instruction
    assert "answer questions" in instruction


def test_missing_gemini_key_returns_safe_failure_without_request(monkeypatch, tmp_path) -> None:
    image = tmp_path / "scan.png"
    image.write_bytes(b"png")
    monkeypatch.setattr(settings, "gemini_api_key", None)
    monkeypatch.setattr(
        gemini.httpx,
        "post",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Gemini should not be called")),
    )

    result = gemini.analyze_document(image, ["English"], datetime.now(timezone.utc))

    assert result.transcription is None
    assert result.category_name == "Needs Review"
    assert result.category_confidence == 0.0
    assert result.error == "GEMINI_API_KEY is not configured"


def test_gemini_api_error_is_readable(monkeypatch, tmp_path) -> None:
    image = tmp_path / "scan.jpg"
    image.write_bytes(b"jpg")
    monkeypatch.setattr(settings, "gemini_api_key", "bad-key")
    monkeypatch.setattr(
        gemini.httpx,
        "post",
        lambda *args, **kwargs: FakeResponse(
            {"error": {"code": 400, "message": "API key not valid"}},
            status_code=400,
        ),
    )

    result = gemini.analyze_document(image, ["Physics"], datetime.now(timezone.utc))

    assert result.category_name == "Needs Review"
    assert result.error == "Gemini document analysis failed: API key not valid"


def test_invalid_fields_fall_back_independently(monkeypatch, tmp_path) -> None:
    image = tmp_path / "scan.jpg"
    image.write_bytes(b"jpg")
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(
        gemini.httpx,
        "post",
        lambda *args, **kwargs: FakeResponse(
            {
                "candidates": [
                    {"content": {"parts": [{"text": '{"transcription":7,"category":"Invented","category_confidence":"high"}'}]}}
                ]
            }
        ),
    )

    result = gemini.analyze_document(image, ["Physics"], datetime(2026, 10, 5, 12, 30, tzinfo=timezone.utc))

    assert result.transcription is None
    assert result.title.startswith("Scan – Oct 5, 2026")
    assert result.category_name == "Needs Review"
    assert result.category_confidence == 0.0
    assert result.error is None


def test_low_confidence_forces_needs_review(monkeypatch, tmp_path) -> None:
    image = tmp_path / "scan.jpg"
    image.write_bytes(b"jpg")
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(
        gemini.httpx,
        "post",
        lambda *args, **kwargs: FakeResponse(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": '{"transcription":"Text","title":"Worksheet","category":"Physics","category_confidence":0.3}'}
                            ]
                        }
                    }
                ]
            }
        ),
    )

    result = gemini.analyze_document(image, ["Physics"], datetime.now(timezone.utc))

    assert result.category_name == "Needs Review"
    assert result.model_category == "Physics"
    assert result.category_confidence == 0.3
