"""Durable conversation history (F05, docs/OPENAGENT_SPEC_MAPPING.md) — store-level
coverage, same pattern as tests/test_enterprise.py: exercise EnterpriseStore directly
rather than the /chat HTTP routes, which need a real model loaded."""

from pathlib import Path

from api.enterprise import EnterpriseStore


def _store(tmp_path: Path) -> EnterpriseStore:
    return EnterpriseStore(tmp_path / "enterprise.db")


def test_conversation_round_trip(tmp_path: Path):
    control = _store(tmp_path)
    conversation_id = control.create_conversation("demo", "alice", "Titre")
    control.add_message("demo", conversation_id, "user", "Salut")
    control.add_message("demo", conversation_id, "assistant", "Bonjour !", ["doc1.md"])

    messages = control.conversation_messages(conversation_id)
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert [m["seq"] for m in messages] == [1, 2]
    assert messages[1]["rag_chunks"] == ["doc1.md"]

    summary = control.conversation("demo", "alice", conversation_id)
    assert summary["title"] == "Titre"


def test_add_message_bumps_updated_at_and_list_orders_by_recency(tmp_path: Path):
    control = _store(tmp_path)
    older = control.create_conversation("demo", "alice", "Ancienne")
    newer = control.create_conversation("demo", "alice", "Récente")
    control.add_message("demo", older, "user", "hello")

    listed = control.list_conversations("demo", "alice")
    assert [c["id"] for c in listed] == [older, newer]  # older bumped after its message
    counts = {c["id"]: c["message_count"] for c in listed}
    assert counts[older] == 1
    assert counts[newer] == 0


def test_conversations_are_isolated_by_project_and_actor(tmp_path: Path):
    control = _store(tmp_path)
    conversation_id = control.create_conversation("demo", "alice", "Titre")

    assert control.conversation("demo", "bob", conversation_id) is None  # different actor
    assert control.conversation("other-project", "alice", conversation_id) is None  # different project
    assert control.list_conversations("demo", "bob") == []
    assert control.conversation("demo", "alice", conversation_id) is not None


def test_rename_requires_ownership(tmp_path: Path):
    control = _store(tmp_path)
    conversation_id = control.create_conversation("demo", "alice", "Titre")
    assert control.rename_conversation("demo", "bob", conversation_id, "Piraté") is False
    assert control.rename_conversation("demo", "alice", conversation_id, "Nouveau titre") is True
    assert control.conversation("demo", "alice", conversation_id)["title"] == "Nouveau titre"


def test_delete_requires_ownership_and_cascades_messages(tmp_path: Path):
    control = _store(tmp_path)
    conversation_id = control.create_conversation("demo", "alice", "Titre")
    control.add_message("demo", conversation_id, "user", "hello")

    assert control.delete_conversation("demo", "bob", conversation_id) is False
    assert control.conversation_messages(conversation_id) != []

    assert control.delete_conversation("demo", "alice", conversation_id) is True
    assert control.conversation("demo", "alice", conversation_id) is None
    assert control.conversation_messages(conversation_id) == []


def test_conversation_title_defaults_and_truncates(tmp_path: Path):
    control = _store(tmp_path)
    empty = control.create_conversation("demo", "alice", "")
    assert control.conversation("demo", "alice", empty)["title"] == "Nouvelle conversation"

    long_title = "x" * 500
    truncated = control.create_conversation("demo", "alice", long_title)
    assert len(control.conversation("demo", "alice", truncated)["title"]) == 200
