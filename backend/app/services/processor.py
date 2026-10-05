import cv2
import numpy as np

from ..config import settings
from ..constants import REVIEW_CATEGORY_NAME
from ..db import SessionLocal
from ..models import Category, Document, ProcessingStatus
from .gemini_document_service import analyze_document
from .document_index import index_document
from .ocr import extract_text
from .scanner import corners_to_json, scan_document, scan_document_with_corners
from .storage import absolute_path, save_jpeg, save_png


def _unsure_category(db, user_id: int) -> Category:
    category = db.query(Category).filter(
        Category.user_id == user_id,
        Category.is_system.is_(True),
    ).first()
    if category is None:
        category = Category(name=REVIEW_CATEGORY_NAME, is_system=True, user_id=user_id)
        db.add(category)
        db.flush()
    return category


def process_document(document_id: int) -> None:
    """Run the expensive scan pipeline outside the request lifecycle."""
    with SessionLocal() as db:
        document = db.get(Document, document_id)
        if document is None:
            return

        try:
            unsure = _unsure_category(db, document.user_id)
            original_path = absolute_path(document.original_image_path)
            image = cv2.imread(str(original_path), cv2.IMREAD_COLOR)
            if image is None:
                raise OSError("The saved original image could not be decoded")

            scan_accepted = False
            analysis_path = original_path
            try:
                scan = scan_document(image)
                document.scan_confidence = scan.detection.confidence
                document.detected_corners = corners_to_json(scan.detection.corners)
                document.scan_debug = scan.detection.debug_info
                document.scanned_image_path = save_jpeg(document.id, "scanned.jpg", scan.color)
                document.bw_image_path = save_png(document.id, "scanned_bw.png", scan.black_and_white)
                analysis_path = absolute_path(document.scanned_image_path)
                scan_accepted = (
                    scan.detection.corners is not None
                    and scan.detection.confidence >= settings.scan_confidence_threshold
                )
            except Exception as exc:
                document.scan_confidence = 0.0
                document.scan_debug = {"scanner_error": f"{type(exc).__name__}: {exc}"}

            categories = db.query(Category).filter(
                Category.user_id == document.user_id
            ).order_by(Category.name).all()
            analysis = analyze_document(
                analysis_path,
                [category.name for category in categories if not category.is_system],
                document.created_at,
            )
            analysis_debug = {
                "provider": "gemini_vision",
                "image": "processed_scan" if analysis_path != original_path else "original_fallback",
                "model_title": analysis.model_title,
                "model_category": analysis.model_category,
                "validated_category": analysis.category_name,
                "category_confidence": analysis.category_confidence,
            }
            if analysis.error:
                # PaddleOCR is intentionally cold unless the Gemini request fails.
                ocr = extract_text(analysis_path)
                document.ocr_text = ocr.text or None
                document.ocr_error = ocr.error
                analysis_debug.update(
                    {
                        "provider": "paddleocr_fallback",
                        "gemini_error": analysis.error,
                        "paddle_error": ocr.error,
                    }
                )
            else:
                document.ocr_text = analysis.transcription
                document.ocr_error = None

            document.title = analysis.title
            document.classification_confidence = analysis.category_confidence
            document.classification_error = analysis.error
            document.scan_debug = {**(document.scan_debug or {}), "document_analysis": analysis_debug}
            selected = next(
                (
                    category
                    for category in categories
                    if category.name.casefold() == analysis.category_name.casefold()
                ),
                unsure,
            )
            document.category_id = selected.id
            document.category = selected
            document.processing_status = (
                ProcessingStatus.complete.value
                if scan_accepted and not selected.is_system
                else ProcessingStatus.needs_review.value
            )
            embedding_error = index_document(document)
            analysis_debug["embedding"] = "failed" if embedding_error else "ready"
            analysis_debug["embedding_model"] = document.embedding_model
            if embedding_error:
                analysis_debug["embedding_error"] = embedding_error
            db.commit()
        except Exception as exc:
            db.rollback()
            document = db.get(Document, document_id)
            if document is not None:
                debug = dict(document.scan_debug or {})
                debug["processing_error"] = f"{type(exc).__name__}: {exc}"
                document.scan_debug = debug
                document.processing_status = ProcessingStatus.failed.value
                db.commit()


def process_document_adjustment(
    document_id: int,
    corners: list[list[float]],
    scan_mode: str,
) -> None:
    """Regenerate a scan from user-confirmed corners outside the request lifecycle."""
    with SessionLocal() as db:
        document = db.get(Document, document_id)
        if document is None:
            return

        try:
            image = cv2.imread(str(absolute_path(document.original_image_path)), cv2.IMREAD_COLOR)
            if image is None:
                raise OSError("The saved original image could not be decoded")
            scan = scan_document_with_corners(image, np.asarray(corners, dtype=np.float32))
            document.scanned_image_path = save_jpeg(document.id, "scanned.jpg", scan.color)
            document.bw_image_path = save_png(document.id, "scanned_bw.png", scan.black_and_white)
            document.detected_corners = corners_to_json(scan.detection.corners)
            document.scan_confidence = scan.detection.confidence
            document.scan_mode = scan_mode
            document.scan_revision = (document.scan_revision or 0) + 1
            document.processing_status = ProcessingStatus.complete.value
            document.scan_debug = {
                **scan.detection.debug_info,
                "manual_adjustment": True,
                "selected_scan_mode": scan_mode,
            }
            db.commit()
        except Exception as exc:
            db.rollback()
            document = db.get(Document, document_id)
            if document is not None:
                debug = dict(document.scan_debug or {})
                debug["manual_adjustment"] = {
                    "status": "failed",
                    "scan_mode": scan_mode,
                    "error": f"{type(exc).__name__}: {exc}",
                }
                document.scan_debug = debug
                document.processing_status = ProcessingStatus.needs_review.value
                db.commit()
