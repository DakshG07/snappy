import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from ..auth import get_current_user
from ..config import settings
from ..db import get_db
from ..models import Document, ProcessingStatus, User
from ..schemas import SearchDebug, SearchResponse, SearchResult
from ..services.document_index import index_document
from ..services.embedding_service import EmbeddingError, EmbeddingService, cosine_similarity
from .documents import _serialize


router = APIRouter(prefix="/search", tags=["search"])
WORD_PATTERN = re.compile(r"[\w'-]+", re.UNICODE)


def _keyword_boost(query: str, document: Document) -> float:
    needle = " ".join(query.casefold().split())
    title = document.title.casefold()
    category = document.category.name.casefold()
    transcription = (document.ocr_text or "").casefold()
    boost = 0.0
    if needle in title:
        boost += 0.08
    elif needle in transcription:
        boost += 0.04
    if needle == category:
        boost += 0.04
    words = {word for word in WORD_PATTERN.findall(needle) if len(word) > 2}
    if words:
        title_words = set(WORD_PATTERN.findall(title))
        body_words = set(WORD_PATTERN.findall(transcription))
        coverage = sum(1 for word in words if word in title_words or word in body_words) / len(words)
        boost += min(0.05, coverage * 0.05)
    return boost


@router.get("", response_model=SearchResponse)
def search_documents(
    q: str = Query(min_length=2, max_length=300),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SearchResponse:
    query = " ".join(q.split()).strip()
    if len(query) < 2:
        raise HTTPException(status_code=422, detail="Enter at least 2 characters to search.")

    provider = EmbeddingService()
    try:
        query_embedding = provider.embed_query(query)
    except EmbeddingError as exc:
        raise HTTPException(status_code=503, detail="Search is temporarily unavailable.") from exc

    documents = (
        db.query(Document)
        .options(joinedload(Document.category))
        .filter(
            Document.user_id == current_user.id,
            Document.ocr_text.is_not(None),
            Document.processing_status.in_(
                [
                    ProcessingStatus.complete.value,
                    ProcessingStatus.needs_review.value,
                    ProcessingStatus.failed.value,
                ]
            ),
        )
        .all()
    )

    # Existing libraries are indexed once, lazily, without delaying app startup.
    changed = False
    for document in documents:
        if not document.embedding_json or document.embedding_model != provider.model:
            index_document(document, provider)
            changed = True
    if changed:
        db.commit()

    ranked: list[tuple[float, float, float, Document]] = []
    for document in documents:
        raw_embedding = document.embedding_json
        if not isinstance(raw_embedding, list):
            continue
        try:
            semantic_score = cosine_similarity(query_embedding, [float(value) for value in raw_embedding])
        except (TypeError, ValueError):
            continue
        if semantic_score is None or semantic_score < settings.semantic_search_min_score:
            continue
        boost = _keyword_boost(query, document)
        score = min(1.0, max(0.0, semantic_score + boost))
        ranked.append((score, semantic_score, boost, document))

    ranked.sort(
        key=lambda item: (item[0], item[3].created_at.timestamp()),
        reverse=True,
    )
    results = [
        SearchResult(
            document=_serialize(document),
            score=round(score, 6),
            debug=(
                SearchDebug(
                    semantic_score=round(semantic_score, 6),
                    keyword_boost=round(boost, 6),
                )
                if settings.debug
                else None
            ),
        )
        for score, semantic_score, boost, document in ranked[: settings.semantic_search_max_results]
    ]
    return SearchResponse(query=query, results=results)
