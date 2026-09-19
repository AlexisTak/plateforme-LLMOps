"""Regression tests for the post-merge review of F05/F07/F14 (docs/OPENAGENT_SPEC_MAPPING.md,
section « Corrections post-revue »). Each test names the finding it pins down.

Same conventions as tests/test_rag_acl.py / tests/test_agent_budget.py: HTTP-level tests hit
the real module-level `store` singleton, so every test uses its own distinctive project id,
and the model is never loaded — `api.routes.chat.Assistant` is monkeypatched."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from rag.retriever import RetrievedChunk

PROXY = {"BISCUITS_AUTH_MODE": "proxy", "BISCUITS_PROXY_SECRET": "test-secret"}


def _headers(actor_id: str, role: str) -> dict[str, str]:
    return {
        "x-biscuits-proxy-secret": "test-secret", "x-biscuits-user-id": actor_id,
        "x-biscuits-user-email": f"{actor_id}@example.test", "x-biscuits-role": role,
    }


def _chunk(doc_id: str, category: str, score: float) -> RetrievedChunk:
    return RetrievedChunk(chunk_id=f"{doc_id}::0", doc_id=doc_id, category=category, text="...", score=score)


def _project(tmp_path: Path, project_id: str) -> Path:
    project = tmp_path / project_id
    project.mkdir()
    (project / "meta.json").write_text('{"base_model": "test-model"}', encoding="utf-8")
    return project


def _chat_client(project: Path, monkeypatch, assistant_cls):
    from api.paths import project_dir
    from api.routes import chat as chat_routes

    monkeypatch.setattr(chat_routes, "Assistant", assistant_cls)
    monkeypatch.setattr(chat_routes.manager, "available_adapters", lambda p: [])
    app = FastAPI()
    app.include_router(chat_routes.router)
    app.dependency_overrides[project_dir] = lambda: project
    return TestClient(app)


class _Result:
    response, rag_used, rag_chunks = "bonjour", False, []


class OkAssistant:
    kwargs: dict = {}

    def __init__(self, **kwargs):
        OkAssistant.kwargs = kwargs

    def run(self, message, **kwargs):
        return _Result()


class FailingAssistant:
    def __init__(self, **kwargs):
        pass

    def run(self, message, **kwargs):
        raise ValueError("modèle non chargé")


# --- 1. F07 ACL must hold on RAG-grounded chat, not only /rag/search ------------


def test_build_context_drops_chunks_outside_allowed_categories(tmp_path: Path, monkeypatch):
    from rag import context_builder

    monkeypatch.setattr(context_builder, "retrieve", lambda q, p, top_k=5: [
        _chunk("guide.md", "methods", 0.9), _chunk("pricing.md", "product", 0.95),
    ])
    unrestricted = context_builder.build_context("x", tmp_path)
    assert {c.doc_id for c in unrestricted.chunks_used} == {"guide.md", "pricing.md"}

    restricted = context_builder.build_context("x", tmp_path, allowed_categories={"methods"})
    assert [c.doc_id for c in restricted.chunks_used] == ["guide.md"]
    assert "pricing.md" not in restricted.context_block


def test_chat_hands_the_callers_category_acl_to_the_assistant(tmp_path: Path, monkeypatch):
    from api.enterprise import store as enterprise_store

    project_id = "review-rag-acl-chat-regression-test"
    project = _project(tmp_path, project_id)
    enterprise_store.set_rag_category_acl(project_id, "product", "admin")
    for key, value in PROXY.items():
        monkeypatch.setenv(key, value)
    enterprise_store.set_member(project_id, "viewer-r1", "viewer-r1@example.test", "Viewer", "viewer")

    client = _chat_client(project, monkeypatch, OkAssistant)
    response = client.post(f"/api/projects/{project_id}/chat", json={"message": "x", "rag": True},
                           headers=_headers("viewer-r1", "viewer"))
    assert response.status_code == 200, response.text
    assert OkAssistant.kwargs["allowed_categories"] == {"methods", "research", "other"}


# --- 4. chat + conversation routes require project membership --------------------


def test_chat_and_conversation_routes_reject_non_members(tmp_path: Path, monkeypatch):
    project_id = "review-chat-membership-regression-test"
    project = _project(tmp_path, project_id)
    for key, value in PROXY.items():
        monkeypatch.setenv(key, value)
    client = _chat_client(project, monkeypatch, OkAssistant)
    headers = _headers("stranger", "viewer")

    assert client.get(f"/api/projects/{project_id}/chat/adapters", headers=headers).status_code == 403
    assert client.get(f"/api/projects/{project_id}/chat/conversations", headers=headers).status_code == 403
    assert client.post(f"/api/projects/{project_id}/chat/conversations", json={}, headers=headers).status_code == 403
    assert client.post(f"/api/projects/{project_id}/chat", json={"message": "x"}, headers=headers).status_code == 403


# --- 3. no orphan conversation on a failed first message ------------------------


def test_failed_first_message_creates_no_conversation(tmp_path: Path, monkeypatch):
    from api.enterprise import store as enterprise_store

    project_id = "review-chat-orphan-regression-test"
    project = _project(tmp_path, project_id)
    client = _chat_client(project, monkeypatch, FailingAssistant)

    response = client.post(f"/api/projects/{project_id}/chat", json={"message": "salut", "persist": True})
    assert response.status_code == 400
    assert enterprise_store.list_conversations(project_id, "local-admin") == []


def test_successful_persisted_exchange_stores_both_turns(tmp_path: Path, monkeypatch):
    from api.enterprise import store as enterprise_store

    project_id = "review-chat-persist-regression-test"
    project = _project(tmp_path, project_id)
    client = _chat_client(project, monkeypatch, OkAssistant)

    first = client.post(f"/api/projects/{project_id}/chat", json={"message": "salut", "persist": True}).json()
    conversation_id = first["conversation_id"]
    assert conversation_id
    second = client.post(f"/api/projects/{project_id}/chat",
                         json={"message": "encore", "conversation_id": conversation_id}).json()
    assert second["conversation_id"] == conversation_id
    roles = [m["role"] for m in enterprise_store.conversation_messages(conversation_id)]
    assert roles == ["user", "assistant", "user", "assistant"]


# --- 5. authentication before the budget gate -----------------------------------


def test_unauthenticated_caller_gets_401_not_429_when_budget_is_spent(tmp_path: Path, monkeypatch):
    from api.enterprise import store as enterprise_store

    project_id = "review-budget-auth-order-regression-test"
    project = _project(tmp_path, project_id)
    enterprise_store.set_agent_budget(project_id, 1, 7_200_000, 500)
    e = enterprise_store.start_execution(project_id, "local-admin", "test-model", None, False, 10)
    enterprise_store.finish_execution(e, response_chars=40, rag_used=False, rag_documents=[], duration_ms=100)
    for key, value in PROXY.items():
        monkeypatch.setenv(key, value)

    client = _chat_client(project, monkeypatch, OkAssistant)
    response = client.post(f"/api/projects/{project_id}/chat", json={"message": "salut"})  # no proxy headers
    assert response.status_code == 401
    assert "jetons" not in response.text


# --- 6. budget usage is members-only ----------------------------------------------


def test_budget_endpoint_rejects_non_members(tmp_path: Path, monkeypatch):
    from api.paths import project_dir
    from api.routes import enterprise as enterprise_routes

    project_id = "review-budget-members-only-regression-test"
    project = _project(tmp_path, project_id)
    for key, value in PROXY.items():
        monkeypatch.setenv(key, value)
    app = FastAPI()
    app.include_router(enterprise_routes.router)
    app.dependency_overrides[project_dir] = lambda: project
    response = TestClient(app).get(f"/api/enterprise/projects/{project_id}/budget", headers=_headers("stranger", "viewer"))
    assert response.status_code == 403
