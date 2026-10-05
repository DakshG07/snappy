from dataclasses import dataclass
import os
from pathlib import Path
from threading import Lock
from typing import Any

from ..config import settings


@dataclass(slots=True)
class OCRResult:
    text: str
    confidence: float | None = None
    error: str | None = None


_engine: Any = None
_engine_lock = Lock()
_inference_lock = Lock()


def _get_engine() -> Any:
    global _engine
    with _engine_lock:
        if _engine is None:
            # PaddleOCR/PaddleX otherwise caches models under ~/.paddlex. Keep
            # runtime state alongside Scanny's local data instead.
            settings.paddle_cache_path.mkdir(parents=True, exist_ok=True)
            os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(settings.paddle_cache_path))
            from paddleocr import PaddleOCR

            try:
                _engine = PaddleOCR(use_doc_orientation_classify=True, use_doc_unwarping=False, use_textline_orientation=True)
            except TypeError:
                _engine = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
    return _engine


def _parse_legacy(result: Any) -> OCRResult:
    lines: list[str] = []
    confidences: list[float] = []
    for page in result or []:
        for item in page or []:
            if len(item) >= 2 and isinstance(item[1], (list, tuple)):
                text, confidence = item[1][0], item[1][1]
                if text:
                    lines.append(str(text))
                    confidences.append(float(confidence))
    return OCRResult("\n".join(lines), sum(confidences) / len(confidences) if confidences else None)


def _parse_v3(result: Any) -> OCRResult:
    lines: list[str] = []
    confidences: list[float] = []
    for page in result or []:
        data = getattr(page, "json", None)
        data = data() if callable(data) else data
        if isinstance(data, dict):
            payload = data.get("res", data)
            texts = payload.get("rec_texts", [])
            scores = payload.get("rec_scores", [])
            lines.extend(str(text) for text in texts if text)
            confidences.extend(float(score) for score in scores)
    return OCRResult("\n".join(lines), sum(confidences) / len(confidences) if confidences else None)


def extract_text(image_path: Path) -> OCRResult:
    try:
        engine = _get_engine()
        # Paddle's predictor is shared to avoid loading several model copies.
        # Serialize inference while allowing the API and scan stages to proceed.
        with _inference_lock:
            if hasattr(engine, "predict"):
                return _parse_v3(engine.predict(str(image_path)))
            return _parse_legacy(engine.ocr(str(image_path), cls=True))
    except ImportError:
        return OCRResult("", error="PaddleOCR is not installed")
    except Exception as exc:  # OCR failure must never lose an upload.
        return OCRResult("", error=f"OCR failed: {type(exc).__name__}: {exc}")
