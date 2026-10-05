from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import search as search_api
from app.config import settings
from app.db import Base
from app.models import Category, Document, ProcessingStatus, User


class FakeEmbeddingService:
    model = "test-embedding"

    def embed_query(self, query: str) -> list[float]:
        assert query
        return [1.0, 0.0, 0.0]

    def embed_document(self, text: str, title: str) -> list[float]:
        return [1.0, 0.0, 0.0]


def _document(title, category, user, embedding):
    return Document(
        title=title,
        category=category,
        user=user,
        original_image_path="original.jpg",
        scanned_image_path="scan.jpg",
        ocr_text=f"# {title}\n\nPractice content for this subject.",
        processing_status=ProcessingStatus.complete.value,
        embedding_json=embedding,
        embedding_model="test-embedding" if embedding else None,
    )


def test_search_threshold_order_and_user_isolation(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as db:
        user = User(email="student@example.com", password_hash="x")
        other = User(email="other@example.com", password_hash="x")
        physics = Category(name="Physics", user=user)
        history = Category(name="History", user=user)
        private = Category(name="Private", user=other)
        best = _document("Momentum Practice Worksheet", physics, user, [0.98, 0.2, 0.0])
        weak = _document("Ancient History", history, user, [0.2, 0.98, 0.0])
        hidden = _document("Private Impulse Notes", private, other, [1.0, 0.0, 0.0])
        db.add_all([best, weak, hidden])
        db.commit()

        monkeypatch.setattr(search_api, "EmbeddingService", FakeEmbeddingService)
        monkeypatch.setattr(settings, "semantic_search_min_score", 0.55)
        response = search_api.search_documents(q="worksheet about impulse", db=db, current_user=user)

        assert [result.document.id for result in response.results] == [best.id]
        assert all(result.document.id != hidden.id for result in response.results)
        assert response.results[0].score >= 0.9
    engine.dispose()


def test_search_lazily_indexes_a_missing_embedding_once(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as db:
        user = User(email="student@example.com", password_hash="x")
        category = Category(name="Biology", user=user)
        document = _document("Cell Division Worksheet", category, user, None)
        db.add(document)
        db.commit()
        calls = []

        def fake_index(target, provider):
            calls.append(target.id)
            target.embedding_json = [1.0, 0.0, 0.0]
            target.embedding_model = provider.model

        monkeypatch.setattr(search_api, "EmbeddingService", FakeEmbeddingService)
        monkeypatch.setattr(search_api, "index_document", fake_index)
        monkeypatch.setattr(settings, "semantic_search_min_score", 0.55)

        first = search_api.search_documents(q="mitosis", db=db, current_user=user)
        second = search_api.search_documents(q="cell division", db=db, current_user=user)

        assert calls == [document.id]
        assert first.results[0].document.id == document.id
        assert second.results[0].document.id == document.id
    engine.dispose()
