import cv2
import numpy as np
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session, joinedload

from ..auth import get_current_user
from ..constants import REVIEW_CATEGORY_NAME
from ..config import settings
from ..db import get_db
from ..models import Category, Document, ProcessingStatus, User
from ..schemas import CategoryBrief, DocumentAdjustment, DocumentRead, DocumentUpdate
from ..services.document_index import refresh_document_embedding
from ..services.gemini_document_service import fallback_title
from ..services.processor import process_document, process_document_adjustment
from ..services.scanner import order_points, validate_quadrilateral
from ..services.storage import (
    InvalidImageError,
    absolute_path,
    delete_document_files,
    media_url,
    save_original,
    validate_image,
)


router = APIRouter(prefix="/documents", tags=["documents"])


def _serialize(document: Document) -> DocumentRead:
    scan_mode = document.scan_mode or "color"
    primary_scan_path = (
        document.bw_image_path
        if scan_mode == "black_and_white" and document.bw_image_path
        else document.scanned_image_path or document.original_image_path
    )
    revision = document.scan_revision or 0
    primary_scan_url = media_url(primary_scan_path) or ""
    bw_image_url = media_url(document.bw_image_path)
    if revision:
        primary_scan_url = f"{primary_scan_url}?v={revision}"
        if bw_image_url:
            bw_image_url = f"{bw_image_url}?v={revision}"
    return DocumentRead(
        id=document.id,
        title=document.title,
        category_id=document.category_id,
        category=CategoryBrief(
            id=document.category.id,
            name=REVIEW_CATEGORY_NAME if document.category.is_system else document.category.name,
            is_system=document.category.is_system,
        ),
        created_at=document.created_at,
        original_image_url=media_url(document.original_image_path) or "",
        scanned_image_url=primary_scan_url,
        bw_image_url=bw_image_url,
        ocr_text=document.ocr_text,
        ocr_error=document.ocr_error,
        classification_error=document.classification_error,
        processing_status=document.processing_status,
        classification_confidence=document.classification_confidence,
        detected_corners=document.detected_corners,
        scan_confidence=document.scan_confidence,
        scan_debug=document.scan_debug,
        scan_mode=scan_mode,
    )


def _get_document(db: Session, document_id: int, user_id: int) -> Document:
    document = (
        db.query(Document)
        .options(joinedload(Document.category))
        .populate_existing()
        .filter(Document.id == document_id, Document.user_id == user_id)
        .first()
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document


def _unsure(db: Session, user_id: int) -> Category:
    category = db.query(Category).filter(
        Category.user_id == user_id,
        Category.is_system.is_(True),
    ).first()
    if not category:
        category = Category(name=REVIEW_CATEGORY_NAME, is_system=True, user_id=user_id)
        db.add(category)
        db.flush()
    return category


@router.post("", response_model=DocumentRead, status_code=status.HTTP_202_ACCEPTED)
def upload_document(
    background_tasks: BackgroundTasks,
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DocumentRead:
    try:
        validated = validate_image(image.file.read(), image.content_type)
    except InvalidImageError as exc:
        raise HTTPException(status_code=415, detail=str(exc))

    unsure = _unsure(db, current_user.id)
    document = Document(
        title="New scan",
        category_id=unsure.id,
        user_id=current_user.id,
        processing_status=ProcessingStatus.uploaded.value,
    )
    db.add(document)
    db.flush()
    document.title = fallback_title(document.created_at)
    db.commit()

    try:
        document.original_image_path = save_original(document.id, validated)
        document.scanned_image_path = document.original_image_path
        document.processing_status = ProcessingStatus.processing.value
        db.commit()
    except Exception as exc:
        document.processing_status = ProcessingStatus.failed.value
        document.scan_debug = {"storage_error": f"{type(exc).__name__}: {exc}"}
        db.commit()
        return _serialize(_get_document(db, document.id, current_user.id))

    background_tasks.add_task(process_document, document.id)
    return _serialize(_get_document(db, document.id, current_user.id))


@router.get("", response_model=list[DocumentRead])
def list_documents(
    category_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[DocumentRead]:
    query = db.query(Document).options(joinedload(Document.category)).filter(
        Document.user_id == current_user.id
    )
    if category_id is not None:
        query = query.filter(Document.category_id == category_id)
    documents = query.order_by(Document.created_at.desc()).all()
    return [_serialize(document) for document in documents]


@router.get("/{document_id}", response_model=DocumentRead)
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DocumentRead:
    return _serialize(_get_document(db, document_id, current_user.id))


@router.patch("/{document_id}", response_model=DocumentRead)
def update_document(
    document_id: int,
    payload: DocumentUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DocumentRead:
    document = _get_document(db, document_id, current_user.id)
    embedding_changed = False
    if payload.title is not None:
        title = " ".join(payload.title.split()).strip()
        if not title:
            raise HTTPException(status_code=422, detail="Title cannot be empty.")
        if document.title != title:
            document.title = title
            embedding_changed = True
    if payload.category_id is not None:
        category = db.query(Category).filter(
            Category.id == payload.category_id,
            Category.user_id == current_user.id,
        ).first()
        if not category:
            raise HTTPException(status_code=404, detail="Folder not found.")
        if document.category_id != category.id:
            document.category_id = category.id
            embedding_changed = True
            if category.is_system:
                document.processing_status = ProcessingStatus.needs_review.value
            elif (
                document.processing_status == ProcessingStatus.needs_review.value
                and (document.scan_confidence or 0.0) >= settings.scan_confidence_threshold
            ):
                document.processing_status = ProcessingStatus.complete.value
    if embedding_changed:
        document.embedding_json = None
        document.embedding_model = None
        document.embedding_updated_at = None
    db.commit()
    if embedding_changed and document.ocr_text:
        background_tasks.add_task(refresh_document_embedding, document.id)
    return _serialize(_get_document(db, document_id, current_user.id))


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    document = _get_document(db, document_id, current_user.id)
    if document.processing_status in {ProcessingStatus.uploaded.value, ProcessingStatus.processing.value}:
        raise HTTPException(status_code=409, detail="Wait for the current scan to finish before deleting it.")
    try:
        delete_document_files(document.id)
    except OSError as exc:
        raise HTTPException(status_code=500, detail="The document files could not be deleted.") from exc
    db.delete(document)
    db.commit()


@router.post("/{document_id}/adjust", response_model=DocumentRead, status_code=status.HTTP_202_ACCEPTED)
def adjust_document_scan(
    document_id: int,
    payload: DocumentAdjustment,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DocumentRead:
    document = _get_document(db, document_id, current_user.id)
    if document.processing_status in {ProcessingStatus.uploaded.value, ProcessingStatus.processing.value}:
        raise HTTPException(status_code=409, detail="Wait for the current scan to finish before adjusting it.")

    image = cv2.imread(str(absolute_path(document.original_image_path)), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=422, detail="The original image could not be decoded.")

    corner_values = payload.corners.model_dump()
    points = np.asarray(
        [
            corner_values["top_left"],
            corner_values["top_right"],
            corner_values["bottom_right"],
            corner_values["bottom_left"],
        ],
        dtype=np.float32,
    )
    valid, validation = validate_quadrilateral(points, image.shape, min_area_ratio=0.01)
    if not valid:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid corner selection: {validation.get('reason', 'invalid geometry')}",
        )
    ordered = order_points(points)
    document.processing_status = ProcessingStatus.processing.value
    document.scan_debug = {
        **(document.scan_debug or {}),
        "manual_adjustment": {
            "status": "processing",
            "scan_mode": payload.scan_mode,
            "corners": np.round(ordered, 1).tolist(),
        },
    }
    db.commit()
    background_tasks.add_task(
        process_document_adjustment,
        document.id,
        ordered.tolist(),
        payload.scan_mode,
    )
    return _serialize(_get_document(db, document_id, current_user.id))
