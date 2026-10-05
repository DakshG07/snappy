from collections.abc import Generator
from datetime import datetime, timedelta, timezone

import cv2
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.api import auth as auth_api
from app.api import categories as categories_api
from app.api import documents as documents_api
from app.api import media as media_api
from app.auth import SESSION_COOKIE, hash_session_token
from app.db import Base, LEGACY_USER_EMAIL, get_db
from app.models import AuthSession, Category, Document, ProcessingStatus, User


@pytest.fixture
def auth_app(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'auth.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_db() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    app = FastAPI()
    app.include_router(auth_api.router, prefix="/api")
    app.include_router(categories_api.router, prefix="/api")
    app.include_router(documents_api.router, prefix="/api")
    app.include_router(media_api.router)
    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(documents_api, "save_original", lambda document_id, _: f"{document_id}/original.png")
    monkeypatch.setattr(documents_api, "process_document", lambda _: None)
    media_root = tmp_path / "media"
    monkeypatch.setattr(media_api, "absolute_path", lambda relative: media_root / relative)
    yield app, session_factory, media_root
    engine.dispose()


def register(client: TestClient, email: str) -> dict:
    response = client.post("/api/auth/register", json={"email": email, "password": "correct-horse"})
    assert response.status_code == 201
    return response.json()


def test_register_me_duplicate_login_and_logout(auth_app) -> None:
    app, session_factory, _ = auth_app
    client = TestClient(app)

    user = register(client, "  Student@Example.COM ")
    assert user["email"] == "student@example.com"
    raw_cookie = client.cookies.get(SESSION_COOKIE)
    assert raw_cookie
    with session_factory() as db:
        saved_user = db.query(User).filter(User.email == "student@example.com").one()
        assert saved_user.password_hash != "correct-horse"
        assert saved_user.password_hash.startswith("$argon2")
        assert db.query(Category).filter_by(
            user_id=saved_user.id, name="Needs Review", is_system=True
        ).one()
        saved_session = db.query(AuthSession).filter_by(user_id=saved_user.id).one()
        assert saved_session.token_hash == hash_session_token(raw_cookie)
        assert saved_session.token_hash != raw_cookie

    assert client.get("/api/auth/me").json() == user
    duplicate = client.post(
        "/api/auth/register",
        json={"email": "STUDENT@example.com", "password": "another-password"},
    )
    assert duplicate.status_code == 409

    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401
    with session_factory() as db:
        assert db.query(AuthSession).count() == 0

    wrong = client.post(
        "/api/auth/login",
        json={"email": "student@example.com", "password": "wrong-password"},
    )
    assert wrong.status_code == 401
    assert wrong.json()["detail"] == "Invalid email or password."
    malformed = client.post(
        "/api/auth/login",
        json={"email": "not-an-email", "password": "x"},
    )
    assert malformed.status_code == 401
    assert malformed.json()["detail"] == "Invalid email or password."
    assert client.post(
        "/api/auth/login",
        json={"email": "student@example.com", "password": "correct-horse"},
    ).status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_user_data_isolation_and_per_user_category_names(auth_app) -> None:
    app, session_factory, media_root = auth_app
    client_a = TestClient(app)
    client_b = TestClient(app)
    user_a = register(client_a, "a@example.com")
    user_b = register(client_b, "b@example.com")

    physics_a = client_a.post("/api/categories", json={"name": "Physics"})
    physics_b = client_b.post("/api/categories", json={"name": "Physics"})
    assert physics_a.status_code == 201
    assert physics_b.status_code == 201
    assert physics_a.json()["id"] != physics_b.json()["id"]

    with session_factory() as db:
        unsure_b = db.query(Category).filter_by(user_id=user_b["id"], is_system=True).one()
        document_b = Document(
            title="B private paper",
            category_id=unsure_b.id,
            user_id=user_b["id"],
            original_image_path="pending/original.png",
            scanned_image_path="pending/scanned.jpg",
            processing_status=ProcessingStatus.complete.value,
        )
        db.add(document_b)
        db.flush()
        document_b.original_image_path = f"{document_b.id}/original.png"
        document_b.scanned_image_path = f"{document_b.id}/scanned.jpg"
        db.commit()
        document_b_id = document_b.id
    private_file = media_root / str(document_b_id) / "original.png"
    private_file.parent.mkdir(parents=True)
    private_file.write_bytes(b"private image")

    assert client_a.get("/api/documents").json() == []
    assert client_a.get(f"/api/documents/{document_b_id}").status_code == 404
    assert client_a.patch(f"/api/documents/{document_b_id}", json={"title": "stolen"}).status_code == 404
    assert client_a.delete(f"/api/documents/{document_b_id}").status_code == 404
    assert client_a.patch(
        f"/api/categories/{physics_b.json()['id']}", json={"name": "Changed"}
    ).status_code == 404
    assert client_a.delete(f"/api/categories/{physics_b.json()['id']}").status_code == 404
    category_ids_a = {item["id"] for item in client_a.get("/api/categories").json()}
    assert physics_b.json()["id"] not in category_ids_a
    assert physics_a.json()["id"] in category_ids_a
    assert user_a["id"] != user_b["id"]
    assert client_a.get(f"/media/{document_b_id}/original.png").status_code == 404
    assert client_b.get(f"/media/{document_b_id}/original.png").content == b"private image"


def test_authenticated_upload_is_owned_and_unauthenticated_upload_is_rejected(auth_app) -> None:
    app, session_factory, _ = auth_app
    client = TestClient(app)
    user = register(client, "uploader@example.com")
    image = np.full((120, 180, 3), 230, dtype=np.uint8)
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    files = {"image": ("paper.png", encoded.tobytes(), "image/png")}

    unauthorized = TestClient(app).post("/api/documents", files=files)
    assert unauthorized.status_code == 401
    uploaded = client.post("/api/documents", files=files)
    assert uploaded.status_code == 202
    with session_factory() as db:
        document = db.get(Document, uploaded.json()["id"])
        assert document is not None
        assert document.user_id == user["id"]


def test_unsure_cannot_be_renamed_or_deleted(auth_app) -> None:
    app, _, _ = auth_app
    client = TestClient(app)
    register(client, "folders@example.com")
    unsure = next(category for category in client.get("/api/categories").json() if category["is_system"])
    assert unsure["name"] == "Needs Review"

    assert client.patch(f"/api/categories/{unsure['id']}", json={"name": "Other"}).status_code == 403
    assert client.delete(f"/api/categories/{unsure['id']}").status_code == 403


def test_assigning_category_completes_a_review_document_with_an_accepted_scan(auth_app) -> None:
    app, session_factory, _ = auth_app
    client = TestClient(app)
    user = register(client, "reviewer@example.com")
    physics = client.post("/api/categories", json={"name": "Physics"}).json()
    with session_factory() as db:
        review = db.query(Category).filter_by(user_id=user["id"], is_system=True).one()
        document = Document(
            title="Momentum worksheet",
            category=review,
            user_id=user["id"],
            original_image_path="1/original.png",
            scanned_image_path="1/scanned.jpg",
            processing_status=ProcessingStatus.needs_review.value,
            scan_confidence=0.95,
        )
        db.add(document)
        db.commit()
        document_id = document.id

    response = client.patch(
        f"/api/documents/{document_id}",
        json={"category_id": physics["id"]},
    )

    assert response.status_code == 200
    assert response.json()["category"]["name"] == "Physics"
    assert response.json()["processing_status"] == ProcessingStatus.complete.value


def test_expired_session_does_not_authenticate(auth_app) -> None:
    app, session_factory, _ = auth_app
    client = TestClient(app)
    user = register(client, "expired@example.com")
    raw_cookie = client.cookies.get(SESSION_COOKIE)
    with session_factory() as db:
        auth_session = db.query(AuthSession).filter_by(user_id=user["id"]).one()
        auth_session.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()

    client.cookies.set(SESSION_COOKIE, raw_cookie)
    assert client.get("/api/auth/me").status_code == 401


def test_first_registration_claims_legacy_library(auth_app) -> None:
    app, session_factory, _ = auth_app
    with session_factory() as db:
        legacy = User(email=LEGACY_USER_EMAIL, password_hash="!legacy-account")
        unsure = Category(name="Unsure", is_system=True, user=legacy)
        document = Document(
            title="Existing paper",
            category=unsure,
            user=legacy,
            original_image_path="1/original.png",
            scanned_image_path="1/scanned.jpg",
            processing_status=ProcessingStatus.complete.value,
        )
        db.add(document)
        db.commit()

    client = TestClient(app)
    new_user = register(client, "owner@example.com")

    with session_factory() as db:
        assert db.query(User).filter(User.email == LEGACY_USER_EMAIL).first() is None
        existing = db.query(Document).filter(Document.title == "Existing paper").one()
        assert existing.user_id == new_user["id"]
        assert existing.category.user_id == new_user["id"]
        assert existing.category.is_system is True
