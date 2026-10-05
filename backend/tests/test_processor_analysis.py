from types import SimpleNamespace

import cv2
import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Category, Document, ProcessingStatus, User
from app.services import processor
from app.services.gemini_document_service import DocumentAnalysis
from app.services.ocr import OCRResult


def _worker_fixture(tmp_path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as session:
        user = User(email="vision@example.com", password_hash="test")
        review = Category(name="Needs Review", is_system=True, user=user)
        physics = Category(name="Physics", user=user)
        document = Document(
            title="New scan",
            category=review,
            user=user,
            original_image_path="1/original.jpg",
            scanned_image_path="1/original.jpg",
            processing_status=ProcessingStatus.processing.value,
        )
        session.add_all([physics, document])
        session.commit()
        document_id = document.id
        physics_id = physics.id
    image = np.full((500, 700, 3), 240, dtype=np.uint8)
    source = tmp_path / "scan.jpg"
    assert cv2.imwrite(str(source), image)
    scan = SimpleNamespace(
        color=image,
        black_and_white=np.full((500, 700), 255, dtype=np.uint8),
        detection=SimpleNamespace(
            confidence=0.95,
            corners=np.asarray([[10, 10], [690, 10], [690, 490], [10, 490]], dtype=np.float32),
            debug_info={"selected_method": "contour"},
        ),
    )
    return engine, session_factory, source, scan, document_id, physics_id


def _patch_scan(monkeypatch, session_factory, source, scan):
    monkeypatch.setattr(processor, "SessionLocal", session_factory)
    monkeypatch.setattr(processor, "absolute_path", lambda _: source)
    monkeypatch.setattr(processor, "scan_document", lambda _: scan)
    monkeypatch.setattr(processor, "save_jpeg", lambda *_: "1/scanned.jpg")
    monkeypatch.setattr(processor, "save_png", lambda *_: "1/scanned_bw.png")
    monkeypatch.setattr(processor, "index_document", lambda *_: None)


def test_processor_never_runs_paddle_when_gemini_succeeds(monkeypatch, tmp_path) -> None:
    engine, session_factory, source, scan, document_id, physics_id = _worker_fixture(tmp_path)
    _patch_scan(monkeypatch, session_factory, source, scan)
    monkeypatch.setattr(
        processor,
        "analyze_document",
        lambda *args: DocumentAnalysis("# Force and Motion", "Force Worksheet", "Physics", 0.93, model_title="Force Worksheet", model_category="Physics"),
    )
    monkeypatch.setattr(
        processor,
        "extract_text",
        lambda *_: (_ for _ in ()).throw(AssertionError("PaddleOCR must stay cold after Gemini success")),
    )

    processor.process_document(document_id)

    with session_factory() as session:
        document = session.get(Document, document_id)
        assert document.ocr_text == "# Force and Motion"
        assert document.title == "Force Worksheet"
        assert document.category_id == physics_id
        assert document.processing_status == ProcessingStatus.complete.value
        assert document.scan_debug["document_analysis"]["provider"] == "gemini_vision"
    engine.dispose()


def test_processor_runs_paddle_only_after_gemini_failure(monkeypatch, tmp_path) -> None:
    engine, session_factory, source, scan, document_id, _ = _worker_fixture(tmp_path)
    _patch_scan(monkeypatch, session_factory, source, scan)
    monkeypatch.setattr(
        processor,
        "analyze_document",
        lambda *args: DocumentAnalysis(None, "Scan – Oct 5, 2026 1:00 PM", "Needs Review", 0.0, "Gemini unavailable"),
    )
    calls: list[str] = []

    def fallback(path):
        calls.append(str(path))
        return OCRResult("Paddle fallback text")

    monkeypatch.setattr(processor, "extract_text", fallback)

    processor.process_document(document_id)

    with session_factory() as session:
        document = session.get(Document, document_id)
        assert calls == [str(source)]
        assert document.ocr_text == "Paddle fallback text"
        assert document.category.is_system is True
        assert document.processing_status == ProcessingStatus.needs_review.value
        assert document.classification_error == "Gemini unavailable"
        assert document.scan_debug["document_analysis"]["provider"] == "paddleocr_fallback"
    engine.dispose()
