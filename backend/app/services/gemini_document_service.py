import base64
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import httpx

from ..config import settings
from ..constants import REVIEW_CATEGORY_NAME


TRANSCRIPTION_INSTRUCTION = """You are transcribing a scanned school document.
Return a faithful Markdown transcription plus concise metadata. Preserve visible wording, organization, and natural reading order. Use Markdown headings, paragraphs, lists, numbered questions, tables, checkboxes, and LaTeX-compatible equations when appropriate. Reconstruct clear row/column relationships and include legible handwriting. Use [illegible] instead of guessing. For meaningful non-text content, use a short neutral marker such as [diagram of a cell]. Do not summarize, paraphrase, explain, answer questions, correct grammar, add knowledge, infer missing content, or describe decorative styling."""


@dataclass(slots=True)
class DocumentAnalysis:
    transcription: str | None
    title: str
    category_name: str
    category_confidence: float
    error: str | None = None
    model_title: str | None = None
    model_category: str | None = None


def fallback_title(created_at: datetime) -> str:
    month = created_at.strftime("%b")
    clock = created_at.strftime("%I:%M %p").lstrip("0")
    return f"Scan – {month} {created_at.day}, {created_at.year} {clock}"


def _mime_type(path: Path) -> str:
    return "image/png" if path.suffix.casefold() == ".png" else "image/jpeg"


def _allowed_categories(categories: list[str]) -> list[str]:
    allowed: list[str] = []
    seen: set[str] = set()
    for name in [*categories, REVIEW_CATEGORY_NAME]:
        cleaned = " ".join(name.split()).strip()
        key = cleaned.casefold()
        if cleaned and key not in seen and key != "unsure":
            seen.add(key)
            allowed.append(cleaned)
    return allowed


def _error_detail(exc: httpx.HTTPStatusError) -> str:
    try:
        payload = exc.response.json().get("error", str(exc))
        return payload.get("message", str(payload)) if isinstance(payload, dict) else str(payload)
    except (ValueError, AttributeError):
        return str(exc)


def analyze_document(image_path: Path, categories: list[str], created_at: datetime) -> DocumentAnalysis:
    """Analyze one processed scan with Gemini Vision in a single structured request."""
    fallback = fallback_title(created_at)
    allowed = _allowed_categories(categories)
    if not settings.gemini_api_key:
        return DocumentAnalysis(None, fallback, REVIEW_CATEGORY_NAME, 0.0, "GEMINI_API_KEY is not configured")

    schema = {
        "type": "object",
        "properties": {
            "transcription": {
                "type": "string",
                "description": "Faithful layout-aware Markdown transcription of only the visible document content.",
            },
            "title": {
                "type": "string",
                "description": "Short descriptive document title, preferring an obvious title visible on the page.",
            },
            "category": {
                "type": "string",
                "enum": allowed,
                "description": f"Exactly one allowed category. Use {REVIEW_CATEGORY_NAME} when uncertain.",
            },
            "category_confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
            },
        },
        "required": ["transcription", "title", "category", "category_confidence"],
    }
    try:
        encoded_image = base64.b64encode(image_path.read_bytes()).decode("ascii")
        response = httpx.post(
            f"{settings.gemini_base_url.rstrip('/')}/v1beta/models/{settings.gemini_model}:generateContent",
            headers={"x-goog-api-key": settings.gemini_api_key, "Content-Type": "application/json"},
            json={
                "systemInstruction": {"parts": [{"text": TRANSCRIPTION_INSTRUCTION}]},
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {"inlineData": {"mimeType": _mime_type(image_path), "data": encoded_image}},
                            {
                                "text": (
                                    "Transcribe and classify this document. Choose exactly one category from: "
                                    f"{json.dumps(allowed)}. Return only the requested structured result."
                                )
                            },
                        ],
                    }
                ],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseJsonSchema": schema,
                    "temperature": 0.0,
                    "maxOutputTokens": settings.gemini_max_output_tokens,
                },
            },
            timeout=httpx.Timeout(settings.gemini_timeout_seconds, connect=8),
        )
        response.raise_for_status()
        body = response.json()
        candidates = body.get("candidates") or []
        if not candidates:
            block_reason = (body.get("promptFeedback") or {}).get("blockReason")
            raise ValueError(f"Gemini returned no candidates{f' ({block_reason})' if block_reason else ''}")
        parts = ((candidates[0].get("content") or {}).get("parts") or [])
        raw = "".join(str(part.get("text", "")) for part in parts)
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("Gemini returned a non-object JSON response")

        raw_transcription = payload.get("transcription")
        transcription = raw_transcription.strip() if isinstance(raw_transcription, str) and raw_transcription.strip() else None
        raw_title = payload.get("title")
        model_title = raw_title if isinstance(raw_title, str) else None
        title = re.sub(r"\s+", " ", model_title or "").strip(" .")[:200] or fallback
        raw_category = payload.get("category")
        model_category = raw_category if isinstance(raw_category, str) else None
        category = next(
            (name for name in allowed if model_category and name.casefold() == model_category.casefold()),
            REVIEW_CATEGORY_NAME,
        )
        raw_confidence = payload.get("category_confidence")
        confidence = (
            float(raw_confidence)
            if isinstance(raw_confidence, (int, float)) and not isinstance(raw_confidence, bool)
            else 0.0
        )
        confidence = max(0.0, min(1.0, confidence))
        if confidence < settings.classification_confidence_threshold:
            category = REVIEW_CATEGORY_NAME
        return DocumentAnalysis(
            transcription=transcription,
            title=title,
            category_name=category,
            category_confidence=confidence,
            model_title=model_title,
            model_category=model_category,
        )
    except httpx.HTTPStatusError as exc:
        error = f"Gemini document analysis failed: {_error_detail(exc)}"
    except Exception as exc:
        error = f"Gemini document analysis failed: {type(exc).__name__}: {exc}"
    return DocumentAnalysis(None, fallback, REVIEW_CATEGORY_NAME, 0.0, error)
