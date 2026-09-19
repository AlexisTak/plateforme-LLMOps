"""Fine-grained RAG access control (F07, docs/OPENAGENT_SPEC_MAPPING.md) —
"Recherche vectorielle filtrée par espace et droits de l'utilisateur". Multi-espace
(Organization/Workspace) stays deliberately out of scope (ADR-0006); this covers the
"droits de l'utilisateur" half: every /rag route now requires project membership
(closing the pre-existing gap where any actor could hit any project's RAG index),
plus a per-category minimum role on top of it.

Route-level tests never touch the real embedding model or Chroma index:
rag.retriever.retrieve is monkeypatched, same pattern as tests/test_rag_evaluation.py."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.enterprise import EnterpriseStore
from rag.retriever import RetrievedChunk


def _chunk(doc_id: str, category: str, score: float) -> RetrievedChunk:
    return RetrievedChunk(chunk_id=f"{doc_id}::0", doc_id=doc_id, category=category, text="...", score=score)


# --- api.enterprise.EnterpriseStore (pure store-level) --------------------------


def test_default_acls_are_viewer_for_every_category(tmp_path: Path):
    control = EnterpriseStore(tmp_path / "enterprise.db")
    acls = control.rag_category_acls("demo")
    assert {a["category"] for a in acls} == {"methods", "research", "product", "other"}
    assert all(a["minimum_role"] == "viewer" for a in acls)


def test_set_rag_category_acl_validates_category_and_role(tmp_path: Path):
    control = EnterpriseStore(tmp_path / "enterprise.db")
    try:
        control.set_rag_category_acl("demo", "not-a-category", "admin")
        assert False, "should have raised"
    except Exception as e:
        assert "category must be one of" in str(e)
    try:
        control.set_rag_category_acl("demo", "product", "superuser")
        assert False, "should have raised"
    except Exception as e:
        assert "Rôle inconnu" in str(e)


def test_rag_categories_allowed_respects_minimum_role(tmp_path: Path):
    control = EnterpriseStore(tmp_path / "enterprise.db")
    control.set_rag_category_acl("demo", "product", "admin")

    assert control.rag_categories_allowed("demo", "viewer") == {"methods", "research", "other"}
    assert control.rag_categories_allowed("demo", "operator") == {"methods", "research", "other"}
    assert control.rag_categories_allowed("demo", "admin") == {"methods", "research", "product", "other"}


def test_set_rag_category_acl_is_idempotent_per_category(tmp_path: Path):
    control = EnterpriseStore(tmp_path / "enterprise.db")
    control.set_rag_category_acl("demo", "product", "operator")
    control.set_rag_category_acl("demo", "product", "admin")  # overwrite, not a second row
    acls = control.rag_category_acls("demo")
    assert [a["minimum_role"] for a in acls if a["category"] == "product"] == ["admin"]


def test_acls_are_isolated_per_project(tmp_path: Path):
    control = EnterpriseStore(tmp_path / "enterprise.db")
    control.set_rag_category_acl("project-a", "product", "admin")
    assert control.rag_categories_allowed("project-a", "operator") == {"methods", "research", "other"}
    assert control.rag_categories_allowed("project-b", "operator") == {"methods", "research", "product", "other"}


# --- api/routes/rag.py (HTTP, local auth mode — every actor resolves to admin) --


def _client(project: Path) -> TestClient:
    from api.paths import project_dir
    from api.routes import rag as rag_routes

    app = FastAPI()
    app.include_router(rag_routes.router)
    app.dependency_overrides[project_dir] = lambda: project
    return TestClient(app)


def test_search_filters_out_restricted_category(tmp_path: Path, monkeypatch):
    from api.enterprise import store as enterprise_store
    from api.routes import rag as rag_routes

    project = tmp_path / "demo"
    enterprise_store.set_rag_category_acl("demo", "product", "admin")
    monkeypatch.setenv("BISCUITS_AUTH_MODE", "proxy")
    monkeypatch.setenv("BISCUITS_PROXY_SECRET", "test-secret")
    enterprise_store.set_member("demo", "viewer-1", "viewer@example.test", "Viewer", "viewer")
    headers = {
        "x-biscuits-proxy-secret": "test-secret", "x-biscuits-user-id": "viewer-1",
        "x-biscuits-user-email": "viewer@example.test", "x-biscuits-role": "viewer",
    }

    monkeypatch.setattr(rag_routes, "retrieve", lambda q, p, top_k=5: [
        _chunk("guide.md", "methods", 0.9), _chunk("pricing.md", "product", 0.8),
    ])
    response = _client(project).post("/api/projects/demo/rag/search", json={"query": "x", "top_k": 5}, headers=headers)
    assert response.status_code == 200
    assert [c["doc_id"] for c in response.json()] == ["guide.md"]


def test_search_rejects_non_member(tmp_path: Path, monkeypatch):
    project = tmp_path / "demo"
    monkeypatch.setenv("BISCUITS_AUTH_MODE", "proxy")
    monkeypatch.setenv("BISCUITS_PROXY_SECRET", "test-secret")
    headers = {
        "x-biscuits-proxy-secret": "test-secret", "x-biscuits-user-id": "stranger",
        "x-biscuits-user-email": "stranger@example.test", "x-biscuits-role": "viewer",
    }
    response = _client(project).post("/api/projects/demo/rag/search", json={"query": "x", "top_k": 5}, headers=headers)
    assert response.status_code == 403


def test_create_document_in_restricted_category_requires_the_acl_role(tmp_path: Path):
    from api.enterprise import store as enterprise_store

    project = tmp_path / "demo"
    enterprise_store.set_rag_category_acl("demo", "product", "admin")
    client = _client(project)  # local auth mode (default) — resolves to admin, so this must succeed
    response = client.post("/api/projects/demo/rag/documents", json={
        "filename": "a.md", "category": "product", "content": "hello",
    })
    assert response.status_code == 200


def test_list_documents_hides_restricted_category(tmp_path: Path, monkeypatch):
    from api.enterprise import store as enterprise_store

    project = tmp_path / "demo"
    (project / "rag" / "documents" / "methods").mkdir(parents=True)
    (project / "rag" / "documents" / "methods" / "a.md").write_text("hi", encoding="utf-8")
    (project / "rag" / "documents" / "product").mkdir(parents=True)
    (project / "rag" / "documents" / "product" / "b.md").write_text("hi", encoding="utf-8")

    enterprise_store.set_rag_category_acl("demo", "product", "admin")
    monkeypatch.setenv("BISCUITS_AUTH_MODE", "proxy")
    monkeypatch.setenv("BISCUITS_PROXY_SECRET", "test-secret")
    enterprise_store.set_member("demo", "viewer-2", "viewer2@example.test", "Viewer", "viewer")
    headers = {
        "x-biscuits-proxy-secret": "test-secret", "x-biscuits-user-id": "viewer-2",
        "x-biscuits-user-email": "viewer2@example.test", "x-biscuits-role": "viewer",
    }
    response = _client(project).get("/api/projects/demo/rag/documents", headers=headers)
    assert response.status_code == 200
    assert [d["filename"] for d in response.json()] == ["a.md"]


def test_update_rag_acl_requires_admin(tmp_path: Path, monkeypatch):
    project = tmp_path / "demo"
    from api.enterprise import store as enterprise_store
    monkeypatch.setenv("BISCUITS_AUTH_MODE", "proxy")
    monkeypatch.setenv("BISCUITS_PROXY_SECRET", "test-secret")
    enterprise_store.set_member("demo", "op-1", "op@example.test", "Operator", "operator")
    headers = {
        "x-biscuits-proxy-secret": "test-secret", "x-biscuits-user-id": "op-1",
        "x-biscuits-user-email": "op@example.test", "x-biscuits-role": "operator",
    }
    client = _client(project)
    denied = client.put("/api/projects/demo/rag/acls", json={"category": "product", "minimum_role": "admin"}, headers=headers)
    assert denied.status_code == 403

    enterprise_store.set_member("demo", "admin-1", "admin@example.test", "Admin", "admin")
    headers["x-biscuits-user-id"] = "admin-1"
    headers["x-biscuits-user-email"] = "admin@example.test"
    headers["x-biscuits-role"] = "admin"
    allowed = client.put("/api/projects/demo/rag/acls", json={"category": "product", "minimum_role": "admin"}, headers=headers)
    assert allowed.status_code == 200
    assert allowed.json() == {"category": "product", "minimum_role": "admin"}
