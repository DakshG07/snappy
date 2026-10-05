import cv2
import numpy as np
from fastapi import BackgroundTasks
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import documents as documents_api
from app.db import Base
from app.models import Category, Document, ProcessingStatus, User
from app.schemas import DocumentAdjustment, DocumentCorners
from app.services import processor


def test_adjustment_queues_background_processing(monkeypatch, tmp_path) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    user = User(email="adjust@example.com", password_hash="test")
    category = Category(name="Unsure", is_system=True, user=user)
    document = Document(
        title="Test scan",
        category=category,
        user=user,
        original_image_path="1/original.png",
        scanned_image_path="1/scanned.jpg",
        processing_status=ProcessingStatus.needs_review.value,
    )
    session.add(document)
    session.commit()

    image = np.full((500, 700, 3), 38, dtype=np.uint8)
    page = np.array([[90, 65], [620, 80], [590, 445], [70, 430]], dtype=np.int32)
    cv2.fillConvexPoly(image, page, (235, 235, 235))
    source = tmp_path / "original.png"
    assert cv2.imwrite(str(source), image)

    monkeypatch.setattr(documents_api, "absolute_path", lambda _: source)
    monkeypatch.setattr(documents_api, "process_document_adjustment", lambda *_: None)
    payload = DocumentAdjustment(
        corners=DocumentCorners(
            top_left=(90, 65),
            top_right=(620, 80),
            bottom_right=(590, 445),
            bottom_left=(70, 430),
        ),
        scan_mode="black_and_white",
    )

    background_tasks = BackgroundTasks()
    response = documents_api.adjust_document_scan(document.id, payload, background_tasks, session, user)

    assert response.processing_status == ProcessingStatus.processing.value
    assert response.scan_mode == "color"
    assert response.scan_debug["manual_adjustment"]["status"] == "processing"
    assert response.scan_debug["manual_adjustment"]["scan_mode"] == "black_and_white"
    assert len(background_tasks.tasks) == 1
    assert background_tasks.tasks[0].args[0] == document.id
    assert background_tasks.tasks[0].args[2] == "black_and_white"

    session.close()
    engine.dispose()


def test_background_adjustment_saves_scan_and_selected_mode(monkeypatch, tmp_path) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as session:
        user = User(email="worker@example.com", password_hash="test")
        category = Category(name="Unsure", is_system=True, user=user)
        document = Document(
            title="Test scan",
            category=category,
            user=user,
            original_image_path="1/original.png",
            scanned_image_path="1/scanned.jpg",
            processing_status=ProcessingStatus.processing.value,
        )
        session.add(document)
        session.commit()
        document_id = document.id

    image = np.full((500, 700, 3), 38, dtype=np.uint8)
    page = np.array([[90, 65], [620, 80], [590, 445], [70, 430]], dtype=np.int32)
    cv2.fillConvexPoly(image, page, (235, 235, 235))
    source = tmp_path / "original.png"
    assert cv2.imwrite(str(source), image)
    monkeypatch.setattr(processor, "SessionLocal", session_factory)
    monkeypatch.setattr(processor, "absolute_path", lambda _: source)
    monkeypatch.setattr(processor, "save_jpeg", lambda *_: "1/scanned.jpg")
    monkeypatch.setattr(processor, "save_png", lambda *_: "1/scanned_bw.png")
    corners = [[90, 65], [620, 80], [590, 445], [70, 430]]

    processor.process_document_adjustment(document_id, corners, "black_and_white")

    with session_factory() as session:
        updated = session.get(Document, document_id)
        assert updated is not None
        assert updated.processing_status == ProcessingStatus.complete.value
        assert updated.scan_mode == "black_and_white"
        assert updated.scan_revision == 1
        assert updated.scan_confidence == 1.0
        assert updated.scan_debug["selected_method"] == "manual"
        assert updated.detected_corners == {
            "top_left": [90.0, 65.0],
            "top_right": [620.0, 80.0],
            "bottom_right": [590.0, 445.0],
            "bottom_left": [70.0, 430.0],
        }

    engine.dispose()


def test_delete_document_removes_record_and_its_files(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    user = User(email="delete@example.com", password_hash="test")
    category = Category(name="Unsure", is_system=True, user=user)
    document = Document(
        title="Delete me",
        category=category,
        user=user,
        original_image_path="1/original.png",
        scanned_image_path="1/scanned.jpg",
        processing_status=ProcessingStatus.complete.value,
    )
    session.add(document)
    session.commit()
    document_id = document.id
    deleted_file_sets: list[int] = []
    monkeypatch.setattr(documents_api, "delete_document_files", deleted_file_sets.append)

    documents_api.delete_document(document_id, session, user)

    assert session.get(Document, document_id) is None
    assert deleted_file_sets == [document_id]
    session.close()
    engine.dispose()
