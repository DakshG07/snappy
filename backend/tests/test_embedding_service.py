import math

from app.config import settings
from app.services.embedding_service import EmbeddingService, cosine_similarity


class FakeResponse:
    def __init__(self, values):
        self._values = values

    def raise_for_status(self):
        return None

    def json(self):
        return {"embedding": {"values": self._values}}


def test_document_and_query_use_retrieval_specific_gemini_requests(monkeypatch) -> None:
    requests = []

    def fake_post(url, **kwargs):
        requests.append((url, kwargs))
        return FakeResponse([3.0, 4.0, 0.0])

    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(settings, "gemini_embedding_model", "gemini-embedding-001")
    monkeypatch.setattr(settings, "gemini_embedding_dimensions", 3)
    monkeypatch.setattr("app.services.embedding_service.httpx.post", fake_post)

    service = EmbeddingService()
    document = service.embed_document("Title: Momentum\n\nImpulse changes momentum.", "Momentum")
    query = service.embed_query("worksheet about impulse")

    assert document == [0.6, 0.8, 0.0]
    assert math.isclose(cosine_similarity(document, query) or 0, 1.0)
    assert requests[0][0].endswith("/models/gemini-embedding-001:embedContent")
    document_request = requests[0][1]["json"]
    query_request = requests[1][1]["json"]
    assert document_request["taskType"] == "RETRIEVAL_DOCUMENT"
    assert document_request["title"] == "Momentum"
    assert document_request["outputDimensionality"] == 3
    assert query_request["taskType"] == "RETRIEVAL_QUERY"
    assert "title" not in query_request


def test_cosine_similarity_rejects_invalid_or_mismatched_vectors() -> None:
    assert cosine_similarity([], []) is None
    assert cosine_similarity([1.0], [1.0, 0.0]) is None
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) is None
