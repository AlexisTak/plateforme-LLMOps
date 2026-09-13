import sqlite3

import pytest

from api.enterprise import EnterpriseStore


def test_targeted_reads_preserve_project_isolation(tmp_path):
    store = EnterpriseStore(tmp_path / "test.db")
    tool = store.set_tool("one", "lookup", "GET", "https://example.test", False, 5, 1000)
    approval = store.request_approval("one", tool["id"], "user", {"query": "example"})
    assert store.tool("one", tool["id"])["name"] == "lookup"
    assert store.approval("one", approval["id"]) == store.approvals("one")[0]
    assert store.tool("two", tool["id"]) is None
    assert store.approval("two", approval["id"]) is None


def test_connections_close_and_failed_transactions_roll_back(tmp_path):
    store = EnterpriseStore(tmp_path / "test.db")
    with pytest.raises(RuntimeError):
        with store._connect() as db:
            db.execute("INSERT INTO quotas(project_id) VALUES ('rollback')")
            raise RuntimeError("abort")
    with pytest.raises(sqlite3.ProgrammingError):
        db.execute("SELECT 1")
    with store._connect() as check:
        assert check.execute("SELECT * FROM quotas WHERE project_id='rollback'").fetchone() is None


def test_execution_history_uses_index_and_bounds_negative_limit(tmp_path):
    store = EnterpriseStore(tmp_path / "test.db")
    for _ in range(3):
        store.start_execution("one", "user", "model", None, False, 5)
    assert len(store.executions("one", -1)) == 1
    with store._connect() as db:
        plan = db.execute("EXPLAIN QUERY PLAN SELECT * FROM executions WHERE project_id=? ORDER BY started_at DESC LIMIT 100", ("one",)).fetchall()
    assert any("executions_project_started" in row["detail"] for row in plan)
    assert not any("TEMP B-TREE" in row["detail"] for row in plan)
