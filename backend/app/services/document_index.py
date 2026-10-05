from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from ..db import SessionLocal
from ..models import Document
from .embedding_service import EmbeddingError, EmbeddingService, build_embedding_text


def index_document(document: Document, service: EmbeddingService | None = None) -> str | None:
    """Update one loaded document's embedding, returning a non-fatal error if indexing fails."""
    document.embedding_json = None
    document.embedding_model = None
    document.embedding_updated_at = None
    if not (document.ocr_text or "").strip():
        return "Document has no transcription to index."
    provider = service or EmbeddingService()
    try:
        document.embedding_json = provider.embed_document(
            build_embedding_text(document),
            document.title,
        )
        document.embedding_model = provider.model
        document.embedding_updated_at = datetime.now(timezone.utc)
        return None
    except EmbeddingError as exc:
        return str(exc)


def refresh_document_embedding(document_id: int) -> None:
    """Refresh an embedding outside the request lifecycle after metadata edits."""
    with SessionLocal() as db:
        document = (
            db.query(Document)
            .options(joinedload(Document.category))
            .filter(Document.id == document_id)
            .first()
        )
        if document is None:
            return
        error = index_document(document)
        debug = dict(document.scan_debug or {})
        debug["semantic_search"] = {
            "embedding": "failed" if error else "ready",
            "model": document.embedding_model,
            **({"error": error} if error else {}),
        }
        document.scan_debug = debug
        db.commit()
