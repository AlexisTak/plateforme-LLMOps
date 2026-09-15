"""Dataset version snapshots must be immutable: re-preparing an existing
version string with different content is rejected rather than silently
overwriting history (CLAUDE.md dataset versioning requirement)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scripts import dataset_versions


def _write_split(project: Path, split: str, examples: list[dict]) -> None:
    path = project / "data" / split / f"{split}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in examples) + "\n", encoding="utf-8")


def _example(example_id: str, user: str) -> dict:
    return {"id": example_id, "messages": [{"role": "user", "content": user}, {"role": "assistant", "content": "ok"}]}


# --- scripts.dataset_versions ------------------------------------------------


def test_snapshot_creates_immutable_manifest(tmp_path: Path):
    project = tmp_path / "demo"
    _write_split(project, "train", [_example("a", "bonjour")])
    _write_split(project, "validation", [])
    _write_split(project, "test", [])

    manifest = dataset_versions.snapshot(project, "v1", seed=42, author="alice@example.test")

    assert manifest["version"] == "v1"
    assert manifest["splits"] == {"train": 1, "validation": 0, "test": 0}
    assert manifest["example_count"] == 1
    assert manifest["sha256"]
    assert (project / "data" / "versions" / "v1" / "train.jsonl").exists()


def test_resnapshotting_identical_content_is_a_noop(tmp_path: Path):
    project = tmp_path / "demo"
    _write_split(project, "train", [_example("a", "bonjour")])
    _write_split(project, "validation", [])
    _write_split(project, "test", [])

    first = dataset_versions.snapshot(project, "v1", seed=42, author="alice@example.test")
    second = dataset_versions.snapshot(project, "v1", seed=42, author="alice@example.test")
    assert first == second


def test_resnapshotting_changed_content_under_same_version_is_rejected(tmp_path: Path):
    project = tmp_path / "demo"
    _write_split(project, "train", [_example("a", "bonjour")])
    _write_split(project, "validation", [])
    _write_split(project, "test", [])
    dataset_versions.snapshot(project, "v1", seed=42, author="alice@example.test")

    _write_split(project, "train", [_example("a", "bonjour — modifié")])
    with pytest.raises(dataset_versions.VersionConflictError):
        dataset_versions.snapshot(project, "v1", seed=42, author="alice@example.test")

    # the original snapshot must be untouched
    original = json.loads((project / "data" / "versions" / "v1" / "train.jsonl").read_text(encoding="utf-8"))
    assert original["messages"][0]["content"] == "bonjour"


def test_diff_reports_added_removed_and_modified(tmp_path: Path):
    project = tmp_path / "demo"
    _write_split(project, "train", [_example("a", "bonjour"), _example("b", "au revoir")])
    _write_split(project, "validation", [])
    _write_split(project, "test", [])
    dataset_versions.snapshot(project, "v1", seed=42, author="alice@example.test")

    _write_split(project, "train", [_example("a", "bonjour — modifié"), _example("c", "nouveau")])
    dataset_versions.snapshot(project, "v2", seed=42, author="alice@example.test")

    result = dataset_versions.diff(project, "v1", "v2")
    assert {e["id"] for e in result["added"]} == {"c"}
    assert {e["id"] for e in result["removed"]} == {"b"}
    assert {e["id"] for e in result["modified"]} == {"a"}


def test_diff_unknown_version_raises(tmp_path: Path):
    project = tmp_path / "demo"
    _write_split(project, "train", [_example("a", "bonjour")])
    dataset_versions.snapshot(project, "v1", seed=42, author="alice@example.test")
    with pytest.raises(FileNotFoundError):
        dataset_versions.diff(project, "v1", "does-not-exist")


def test_version_used_as_path_segment_rejects_traversal(tmp_path: Path):
    """A version string becomes a directory name under data/versions/ — it must
    never be able to escape that directory (CLAUDE.md §23, path traversal)."""
    project = tmp_path / "demo"
    _write_split(project, "train", [_example("a", "bonjour")])
    for hostile in ("..", "../../etc", "a/b", "/etc/passwd"):
        with pytest.raises(dataset_versions.InvalidVersionError):
            dataset_versions.snapshot(project, hostile, seed=42, author="alice@example.test")
        with pytest.raises(dataset_versions.InvalidVersionError):
            dataset_versions.get_version(project, hostile)


# --- api/routes/dataset.py ----------------------------------------------------


def _client(project: Path) -> TestClient:
    from api.paths import project_dir
    from api.routes import dataset as dataset_routes

    app = FastAPI()
    app.include_router(dataset_routes.router)
    app.dependency_overrides[project_dir] = lambda: project
    return TestClient(app)


def test_prepare_endpoint_snapshots_and_is_idempotent(tmp_path: Path):
    project = tmp_path / "demo"
    (project / "datasets" / "core").mkdir(parents=True)
    (project / "datasets" / "core" / "a.jsonl").write_text(
        json.dumps({"messages": [{"role": "user", "content": "salut"}, {"role": "assistant", "content": "hey"}]}) + "\n",
        encoding="utf-8",
    )
    client = _client(project)

    first = client.post("/api/projects/demo/dataset/prepare", json={"version": "v1", "seed": 42})
    assert first.status_code == 200
    assert first.json()["sha256"]

    second = client.post("/api/projects/demo/dataset/prepare", json={"version": "v1", "seed": 42})
    assert second.status_code == 200
    assert second.json()["sha256"] == first.json()["sha256"]

    listed = client.get("/api/projects/demo/dataset/versions")
    assert listed.status_code == 200
    assert [v["version"] for v in listed.json()] == ["v1"]

    detail = client.get("/api/projects/demo/dataset/versions/v1")
    assert detail.status_code == 200
    assert detail.json()["sha256"] == first.json()["sha256"]


def test_prepare_endpoint_rejects_silent_overwrite_of_a_version(tmp_path: Path):
    project = tmp_path / "demo"
    (project / "datasets" / "core").mkdir(parents=True)
    (project / "datasets" / "core" / "a.jsonl").write_text(
        json.dumps({"messages": [{"role": "user", "content": "salut"}, {"role": "assistant", "content": "hey"}]}) + "\n",
        encoding="utf-8",
    )
    client = _client(project)
    client.post("/api/projects/demo/dataset/prepare", json={"version": "v1", "seed": 42})

    (project / "datasets" / "core" / "b.jsonl").write_text(
        json.dumps({"messages": [{"role": "user", "content": "autre chose"}, {"role": "assistant", "content": "hey"}]}) + "\n",
        encoding="utf-8",
    )
    conflict = client.post("/api/projects/demo/dataset/prepare", json={"version": "v1", "seed": 42})
    assert conflict.status_code == 409


def test_version_endpoints_reject_path_traversal(tmp_path: Path):
    """".." itself never reaches our handler — httpx/Starlette normalize it out of
    the URL before routing (verified below: 404, not a 200 that read outside
    data/versions/). scripts.dataset_versions has the authoritative test for the
    traversal guard itself (test_version_used_as_path_segment_rejects_traversal);
    this only checks a non-".."-shaped invalid version surfaces as 400, not 500."""
    project = tmp_path / "demo"
    (project / "datasets" / "core").mkdir(parents=True)
    client = _client(project)

    prepare = client.post("/api/projects/demo/dataset/prepare", json={"version": "..", "seed": 42})
    assert prepare.status_code == 422  # rejected by the schema pattern before it ever becomes a path

    normalized_away = client.get("/api/projects/demo/dataset/versions/..")
    assert normalized_away.status_code == 404

    get_response = client.get("/api/projects/demo/dataset/versions/v1%20bad")
    assert get_response.status_code == 400

    diff_response = client.get("/api/projects/demo/dataset/versions/v1%20bad/diff/v2%20bad")
    assert diff_response.status_code == 400
