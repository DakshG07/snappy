import math
from typing import Any

import httpx

from ..config import settings


class EmbeddingError(RuntimeError):
    pass


def build_embedding_text(document: Any) -> str:
    """Build the single canonical text representation used by document search."""
    category_name = getattr(getattr(document, "category", None), "name", "")
    transcription = (getattr(document, "ocr_text", None) or "").strip()
    return (
        f"Title: {document.title}\n"
        f"Category: {category_name}\n\n"
        f"{transcription}"
    ).strip()


def normalize_embedding(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in values))
    if not values or not math.isfinite(norm) or norm <= 0:
        raise EmbeddingError("The embedding provider returned an invalid vector.")
    normalized = [value / norm for value in values]
    if not all(math.isfinite(value) for value in normalized):
        raise EmbeddingError("The embedding provider returned non-finite values.")
    return normalized


def cosine_similarity(left: list[float], right: list[float]) -> float | None:
    if not left or len(left) != len(right):
        return None
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm <= 0 or right_norm <= 0:
        return None
    score = sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)
    return score if math.isfinite(score) else None


class EmbeddingService:
    """Gemini embedding adapter; search and indexing stay provider-agnostic."""

    @property
    def model(self) -> str:
        return settings.gemini_embedding_model

    def embed_document(self, text: str, title: str) -> list[float]:
        return self._embed(text, task_type="RETRIEVAL_DOCUMENT", title=title)

    def embed_query(self, query: str) -> list[float]:
        return self._embed(query, task_type="RETRIEVAL_QUERY")

    def _embed(self, text: str, *, task_type: str, title: str | None = None) -> list[float]:
        if not settings.gemini_api_key:
            raise EmbeddingError("GEMINI_API_KEY is not configured.")
        content = text.strip()
        if not content:
            raise EmbeddingError("There is no text to embed.")
        content = content[: settings.embedding_max_input_chars]
        # The raw v1beta REST endpoint currently honors retrieval and dimension
        # options as top-level EmbedContentRequest fields. The SDK exposes the
        # same options through EmbedContentConfig.
        request_body: dict[str, Any] = {
            "model": f"models/{self.model}",
            "content": {"parts": [{"text": content}]},
            "taskType": task_type,
            "outputDimensionality": settings.gemini_embedding_dimensions,
        }
        if title and task_type == "RETRIEVAL_DOCUMENT":
            request_body["title"] = title[:200]
        try:
            response = httpx.post(
                (
                    f"{settings.gemini_base_url.rstrip('/')}/v1beta/models/"
                    f"{self.model}:embedContent"
                ),
                headers={"x-goog-api-key": settings.gemini_api_key, "Content-Type": "application/json"},
                json=request_body,
                timeout=httpx.Timeout(settings.gemini_embedding_timeout_seconds, connect=8),
            )
            response.raise_for_status()
            raw_values = (response.json().get("embedding") or {}).get("values")
            if not isinstance(raw_values, list) or not raw_values:
                raise EmbeddingError("The embedding provider returned no vector.")
            values = [float(value) for value in raw_values]
            if len(values) != settings.gemini_embedding_dimensions:
                raise EmbeddingError(
                    f"The embedding provider returned {len(values)} dimensions; "
                    f"expected {settings.gemini_embedding_dimensions}."
                )
            return normalize_embedding(values)
        except EmbeddingError:
            raise
        except httpx.HTTPStatusError as exc:
            try:
                detail = (exc.response.json().get("error") or {}).get("message")
            except (ValueError, AttributeError):
                detail = None
            raise EmbeddingError(detail or f"Embedding request failed ({exc.response.status_code}).") from exc
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            raise EmbeddingError(f"Embedding request failed: {type(exc).__name__}: {exc}") from exc
