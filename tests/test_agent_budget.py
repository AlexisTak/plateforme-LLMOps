"""Per-agent token/duration/tool-call budgets (F14, docs/OPENAGENT_SPEC_MAPPING.md).
An "agent" in this app is a project (F03). Enforcement is checked before-the-fact,
same style as api/routes/enterprise.py::enforce_job_quota — it blocks the *next*
chat exchange or tool call once today's budget is already spent, it doesn't cut a
running generation off mid-stream.

Route-level tests never touch a real model or network: the token/duration budget
is exhausted purely through store.start_execution/finish_execution (no Assistant
involved before enforce_agent_budget runs), and the tool-call budget is exhausted
through store.audit (no HTTP call before it runs either)."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.enterprise import EnterpriseStore


def _store(tmp_path: Path) -> EnterpriseStore:
    return EnterpriseStore(tmp_path / "enterprise.db")


# --- api.enterprise.EnterpriseStore (pure store-level) --------------------------


def test_default_budget_is_generous(tmp_path: Path):
    control = _store(tmp_path)
    budget = control.agent_budget("demo")
    assert budget["max_tokens_per_day"] == 200_000
    assert budget["max_duration_ms_per_day"] == 7_200_000
    assert budget["max_tool_calls_per_day"] == 500


def test_set_agent_budget_is_idempotent_per_project(tmp_path: Path):
    control = _store(tmp_path)
    control.set_agent_budget("demo", 1000, 60_000, 10)
    control.set_agent_budget("demo", 2000, 120_000, 20)  # overwrite, not a second row
    budget = control.agent_budget("demo")
    assert budget == {"project_id": "demo", "max_tokens_per_day": 2000,
                       "max_duration_ms_per_day": 120_000, "max_tool_calls_per_day": 20}


def test_budgets_are_isolated_per_project(tmp_path: Path):
    control = _store(tmp_path)
    control.set_agent_budget("project-a", 1000, 60_000, 10)
    assert control.agent_budget("project-b")["max_tokens_per_day"] == 200_000


def test_usage_sums_tokens_and_duration_from_executions(tmp_path: Path):
    control = _store(tmp_path)
    e1 = control.start_execution("demo", "alice", "model", None, False, 10)
    control.finish_execution(e1, response_chars=400, rag_used=False, rag_documents=[], duration_ms=1200)
    e2 = control.start_execution("demo", "alice", "model", None, False, 10)
    control.finish_execution(e2, response_chars=400, rag_used=False, rag_documents=[], duration_ms=800)

    usage = control.agent_budget_usage("demo")
    assert usage["tokens_used"] == 200  # (400+400)/4, matches finish_execution's estimate
    assert usage["duration_ms_used"] == 2000
    assert usage["tool_calls_used"] == 0


def test_usage_counts_direct_and_approved_tool_calls(tmp_path: Path):
    control = _store(tmp_path)
    control.audit("alice", "tool.executed", "tool", "t1", "demo")
    control.audit("alice", "tool.approval.approved", "approval", "a1", "demo")
    control.audit("alice", "tool.approval.rejected", "approval", "a2", "demo")  # not a call
    control.audit("alice", "tool.executed", "tool", "t1", "other-project")  # different project

    usage = control.agent_budget_usage("demo")
    assert usage["tool_calls_used"] == 2


# --- api/routes/enterprise.py (HTTP, local auth mode — every actor resolves to admin) --


def _client(project: Path) -> TestClient:
    from api.paths import project_dir
    from api.routes import enterprise as enterprise_routes

    app = FastAPI()
    app.include_router(enterprise_routes.router)
    app.dependency_overrides[project_dir] = lambda: project
    return TestClient(app)


def test_budget_endpoint_reports_usage(tmp_path: Path):
    # Distinct, unlikely-to-collide project id: these HTTP-level tests hit the real
    # module-level `store` singleton (same convention as tests/test_opportunities_routes.py
    # ::test_analyze_rejects_project_the_actor_is_not_a_member_of), not an isolated tmp DB —
    # a shared id like "demo" would pick up other tests' audit events for "today".
    project_id = "agent-budget-usage-regression-test"
    from api.enterprise import store as enterprise_store
    project = tmp_path / project_id
    project.mkdir()
    client = _client(project)

    enterprise_store.start_execution(project_id, "local-admin", "model", None, False, 10)
    response = client.get(f"/api/enterprise/projects/{project_id}/budget")
    assert response.status_code == 200
    body = response.json()
    assert body["max_tokens_per_day"] == 200_000
    assert body["tool_calls_used"] == 0


def test_update_budget_requires_admin(tmp_path: Path, monkeypatch):
    project_id = "agent-budget-admin-regression-test"
    project = tmp_path / project_id
    project.mkdir()
    client = _client(project)

    monkeypatch.setenv("BISCUITS_AUTH_MODE", "proxy")
    monkeypatch.setenv("BISCUITS_PROXY_SECRET", "test-secret")
    viewer_headers = {
        "x-biscuits-proxy-secret": "test-secret", "x-biscuits-user-id": "viewer-1",
        "x-biscuits-user-email": "viewer@example.test", "x-biscuits-role": "viewer",
    }
    denied = client.put(f"/api/enterprise/projects/{project_id}/budget",
                        json={"max_tokens_per_day": 5, "max_duration_ms_per_day": 5, "max_tool_calls_per_day": 5},
                        headers=viewer_headers)
    assert denied.status_code == 403

    admin_headers = {**viewer_headers, "x-biscuits-user-id": "admin-1", "x-biscuits-role": "admin"}
    allowed = client.put(f"/api/enterprise/projects/{project_id}/budget",
                         json={"max_tokens_per_day": 5, "max_duration_ms_per_day": 5, "max_tool_calls_per_day": 5},
                         headers=admin_headers)
    assert allowed.status_code == 200
    assert allowed.json()["max_tokens_per_day"] == 5


def test_execute_tool_blocked_once_tool_call_budget_is_spent(tmp_path: Path):
    project_id = "agent-budget-tool-calls-regression-test"
    from api.enterprise import store as enterprise_store
    project = tmp_path / project_id
    project.mkdir()
    client = _client(project)

    tool = enterprise_store.set_tool(project_id, "ping", "GET", "http://localhost:9/ping",
                                     approval_required=False, timeout_seconds=5, max_response_bytes=1000)
    enterprise_store.set_agent_budget(project_id, 200_000, 7_200_000, 1)
    enterprise_store.audit("local-admin", "tool.executed", "tool", tool["id"], project_id)  # spends the one call

    response = client.post(f"/api/enterprise/projects/{project_id}/tools/{tool['id']}/execute", json={"arguments": {}})
    assert response.status_code == 429
    assert "outils" in response.json()["detail"]


# --- api/routes/chat.py (HTTP) --------------------------------------------------


def test_chat_blocked_once_token_budget_is_spent(tmp_path: Path):
    project_id = "agent-budget-tokens-regression-test"
    from api.enterprise import store as enterprise_store
    from api.paths import project_dir
    from api.routes import chat as chat_routes

    project = tmp_path / project_id
    project.mkdir()
    (project / "meta.json").write_text('{"base_model": "test-model"}', encoding="utf-8")

    enterprise_store.set_agent_budget(project_id, 1, 7_200_000, 500)  # 1 token/day — spent by any real execution
    e = enterprise_store.start_execution(project_id, "local-admin", "test-model", None, False, 10)
    enterprise_store.finish_execution(e, response_chars=40, rag_used=False, rag_documents=[], duration_ms=100)

    app = FastAPI()
    app.include_router(chat_routes.router)
    app.dependency_overrides[project_dir] = lambda: project
    client = TestClient(app)

    response = client.post(f"/api/projects/{project_id}/chat", json={"message": "salut"})
    assert response.status_code == 429
    assert "jetons" in response.json()["detail"]


def test_chat_blocked_once_duration_budget_is_spent(tmp_path: Path):
    project_id = "agent-budget-duration-regression-test"
    from api.enterprise import store as enterprise_store
    from api.paths import project_dir
    from api.routes import chat as chat_routes

    project = tmp_path / project_id
    project.mkdir()
    (project / "meta.json").write_text('{"base_model": "test-model"}', encoding="utf-8")

    enterprise_store.set_agent_budget(project_id, 200_000, 1, 500)  # 1 ms/day — spent by any real execution
    e = enterprise_store.start_execution(project_id, "local-admin", "test-model", None, False, 10)
    enterprise_store.finish_execution(e, response_chars=40, rag_used=False, rag_documents=[], duration_ms=100)

    app = FastAPI()
    app.include_router(chat_routes.router)
    app.dependency_overrides[project_dir] = lambda: project
    client = TestClient(app)

    response = client.post(f"/api/projects/{project_id}/chat", json={"message": "salut"})
    assert response.status_code == 429
    assert "durée" in response.json()["detail"]
