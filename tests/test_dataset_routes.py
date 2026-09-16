"""category is a dynamic directory name (no fixed enum) joined onto a filesystem
path for read/write/delete (api/routes/dataset.py::_category_dir) — must never
accept traversal out of <project>/datasets/."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.paths import project_dir
from api.routes import dataset


def _client(project: Path) -> TestClient:
    app = FastAPI()
    app.include_router(dataset.router)
    app.dependency_overrides[project_dir] = lambda: project
    return TestClient(app)


def test_category_dir_rejects_path_traversal(tmp_path: Path):
    """Direct unit test of the fix, independent of how an HTTP client would encode a
    traversal attempt — a category is joined onto a filesystem path for read/write/
    delete (list_examples/add_example/update_example/delete_example), so it must
    never resolve outside <project>/datasets/, whatever the input looks like."""
    from fastapi import HTTPException

    outside = tmp_path / "secret"
    outside.mkdir()
    (outside / "leak.jsonl").write_text('{"id":"x","messages":[]}\n', encoding="utf-8")

    project = tmp_path / "demo"
    (project / "datasets").mkdir(parents=True)

    for traversal_category in ("../secret", "..", "/etc", "..secret", ""):
        try:
            dataset._category_dir(project, traversal_category)
            assert False, f"expected HTTPException for {traversal_category!r}"
        except HTTPException as exc:
            assert exc.status_code == 404, traversal_category


def test_list_examples_rejects_path_traversal_category_over_http(tmp_path: Path):
    # A literal ".." path segment gets normalized away by HTTP clients before it
    # reaches the server, so the realistic over-the-wire probe is a dot-leading
    # name that isn't a real category — still must not fall through to a 200.
    project = tmp_path / "demo"
    (project / "datasets").mkdir(parents=True)
    client = _client(project)
    response = client.get("/api/projects/demo/dataset/..secret")
    assert response.status_code == 404


def test_list_examples_still_works_for_a_real_category(tmp_path: Path):
    project = tmp_path / "demo"
    category_dir = project / "datasets" / "conversations"
    category_dir.mkdir(parents=True)
    (category_dir / "a.jsonl").write_text(
        '{"id":"1","messages":[{"role":"user","content":"hi"},{"role":"assistant","content":"yo"}]}\n',
        encoding="utf-8",
    )
    client = _client(project)
    response = client.get("/api/projects/demo/dataset/conversations")
    assert response.status_code == 200
    assert len(response.json()) == 1
