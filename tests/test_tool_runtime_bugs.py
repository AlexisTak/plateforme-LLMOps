from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.enterprise import EnterpriseStore
from api.paths import project_dir
from api.routes import enterprise


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    project = tmp_path / "demo"
    project.mkdir()
    store = EnterpriseStore(tmp_path / "control.db")
    monkeypatch.setenv("BISCUITS_AUTH_MODE", "local")
    monkeypatch.setattr(enterprise, "store", store)
    app = FastAPI()
    app.include_router(enterprise.router)
    app.dependency_overrides[project_dir] = lambda: project
    tool = store.set_tool("demo", "read", "GET", "https://example.test", True, 5, 1000)
    approval = store.request_approval("demo", tool["id"], "alice", {})
    return store, tool, approval, TestClient(app, raise_server_exceptions=False)


def test_disabled_tool_cannot_be_approved(runtime, monkeypatch):
    store, tool, approval, client = runtime
    with store._connect() as db:
        db.execute("UPDATE tools SET enabled=0 WHERE id=?", (tool["id"],))
    calls = []
    monkeypatch.setattr(enterprise, "_execute_tool", lambda *args: calls.append(args))
    response = client.post(f"/api/enterprise/projects/demo/approvals/{approval['id']}/decision", json={"decision": "approved"})
    assert response.status_code == 409
    assert not calls
    assert store.approval("demo", approval["id"])["status"] == "pending"


def test_unexpected_tool_error_finalizes_approval(runtime, monkeypatch):
    store, tool, approval, client = runtime
    def fail(*args):
        raise RuntimeError("private exception detail")
    monkeypatch.setattr(enterprise, "_execute_tool", fail)
    response = client.post(f"/api/enterprise/projects/demo/approvals/{approval['id']}/decision", json={"decision": "approved"})
    assert response.status_code == 500
    result = store.approval("demo", approval["id"])
    assert result["status"] == "failed"
    assert "private exception detail" not in str(result)


def test_mcp_business_error_is_not_completed(runtime, monkeypatch):
    store, tool, approval, client = runtime
    class FailedClient:
        def call_tool(self, *args):
            return {"isError": True, "content": [{"type": "text", "text": "not found"}]}
    monkeypatch.setattr(enterprise, "_mcp_client", lambda *args: FailedClient())
    with store._connect() as db:
        db.execute("UPDATE tools SET connector_type='mcp',connector_id='server',action='read' WHERE id=?", (tool["id"],))
    response = client.post(f"/api/enterprise/projects/demo/approvals/{approval['id']}/decision", json={"decision": "approved"})
    assert response.status_code == 502
    assert store.approval("demo", approval["id"])["status"] == "failed"


def test_concurrent_claim_and_denial_only_one_wins(runtime):
    store, tool, approval, client = runtime
    barrier = Barrier(2)
    def decide(claim):
        barrier.wait(timeout=5)
        try:
            if claim:
                store.claim_approval("demo", approval["id"])
            else:
                store.decide_approval("demo", approval["id"], "denied", "reviewer")
            return "success"
        except HTTPException as exc:
            return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(decide, [True, False]))
    assert results.count("success") == 1
    assert results.count(409) == 1
