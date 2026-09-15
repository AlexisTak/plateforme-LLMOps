"""Retrieval quality (Recall@K / MRR) against a labeled query set — CPU only,
never touches the real embedding model or Chroma index: rag.retriever.retrieve
is monkeypatched with fixed chunks, same pattern as tests/test_rag_injection.py
uses for RetrievedChunk fixtures."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from rag import evaluation as rag_evaluation
from rag.retriever import RetrievedChunk


def _chunk(doc_id: str, score: float) -> RetrievedChunk:
    return RetrievedChunk(chunk_id=f"{doc_id}::0", doc_id=doc_id, category="methods", text="...", score=score)


# --- rag.evaluation -----------------------------------------------------------


def test_evaluate_computes_recall_and_mrr(tmp_path: Path, monkeypatch):
    project = tmp_path / "demo"
    rag_evaluation.save_eval_queries(project, [
        {"id": "q1", "query": "how to reset", "relevant_doc_ids": ["guide.md"]},
        {"id": "q2", "query": "pricing", "relevant_doc_ids": ["pricing.md"]},
        {"id": "q3", "query": "unrelated", "relevant_doc_ids": ["nope.md"]},
    ])

    def fake_retrieve(query, project_dir, top_k=5):
        return {
            "how to reset": [_chunk("other.md", 0.9), _chunk("guide.md", 0.8)],  # relevant at rank 2
            "pricing": [_chunk("pricing.md", 0.95)],  # relevant at rank 1
            "unrelated": [_chunk("other.md", 0.5)],  # never retrieved
        }[query]

    monkeypatch.setattr(rag_evaluation, "retrieve", fake_retrieve)

    result = rag_evaluation.evaluate(project, top_k=5)

    assert result["n_queries"] == 3
    assert result["recall_at_k"] == round(2 / 3, 3)
    assert result["mrr"] == round((1 / 2 + 1 / 1 + 0) / 3, 3)
    by_id = {q["id"]: q for q in result["queries"]}
    assert by_id["q1"]["rank"] == 2
    assert by_id["q2"]["hit"] is True
    assert by_id["q3"]["hit"] is False
    assert by_id["q3"]["chunks"][0]["doc_id"] == "other.md"  # auditable: the actual chunks are exposed


def test_evaluate_with_no_queries_returns_null_metrics(tmp_path: Path):
    project = tmp_path / "demo"
    assert rag_evaluation.evaluate(project) == {"top_k": 5, "n_queries": 0, "recall_at_k": None, "mrr": None, "queries": []}


def test_save_then_load_eval_queries_round_trips(tmp_path: Path):
    project = tmp_path / "demo"
    queries = [{"id": "q1", "query": "hi", "relevant_doc_ids": ["a.md"]}]
    rag_evaluation.save_eval_queries(project, queries)
    assert rag_evaluation.load_eval_queries(project) == queries


# --- api/routes/rag.py ---------------------------------------------------------


def _client(project: Path) -> TestClient:
    from api.paths import project_dir
    from api.routes import rag as rag_routes

    app = FastAPI()
    app.include_router(rag_routes.router)
    app.dependency_overrides[project_dir] = lambda: project
    return TestClient(app)


def test_eval_queries_crud_and_evaluate_endpoint(tmp_path: Path, monkeypatch):
    from api.routes import rag as rag_routes

    project = tmp_path / "demo"
    client = _client(project)

    created = client.post("/api/projects/demo/rag/eval-queries", json={
        "id": "q1", "query": "how to reset", "relevant_doc_ids": ["guide.md"],
    })
    assert created.status_code == 201

    duplicate = client.post("/api/projects/demo/rag/eval-queries", json={
        "id": "q1", "query": "again", "relevant_doc_ids": ["guide.md"],
    })
    assert duplicate.status_code == 409

    listed = client.get("/api/projects/demo/rag/eval-queries")
    assert [q["id"] for q in listed.json()] == ["q1"]

    monkeypatch.setattr(rag_routes.rag_evaluation, "retrieve", lambda q, p, top_k=5: [_chunk("guide.md", 0.9)])
    evaluated = client.post("/api/projects/demo/rag/evaluate")
    assert evaluated.status_code == 200
    assert evaluated.json()["recall_at_k"] == 1.0

    deleted = client.delete("/api/projects/demo/rag/eval-queries/q1")
    assert deleted.status_code == 200
    assert client.get("/api/projects/demo/rag/eval-queries").json() == []

    empty = client.post("/api/projects/demo/rag/evaluate")
    assert empty.status_code == 400


def test_delete_unknown_eval_query_is_404(tmp_path: Path):
    project = tmp_path / "demo"
    client = _client(project)
    response = client.delete("/api/projects/demo/rag/eval-queries/does-not-exist")
    assert response.status_code == 404
