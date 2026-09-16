"""project_dir (api/paths.py) resolves a raw URL path segment onto the filesystem
and is the shared dependency for nearly every project-scoped route (dataset, rag,
training, evaluation, chat, enterprise, experiments...). It must never accept
traversal, whatever a client's percent-encoding does to a single path segment."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from api import paths


def test_project_dir_rejects_path_traversal(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(paths, "PROJECTS_DIR", tmp_path / "projects")
    (tmp_path / "projects").mkdir()
    # A real project one level above PROJECTS_DIR, reachable only via traversal.
    (tmp_path / "meta.json").write_text("{}", encoding="utf-8")

    for traversal_id in ("..", "../secret", "/etc", "", "UPPER", "has space"):
        with pytest.raises(HTTPException) as exc_info:
            paths.project_dir(traversal_id)
        assert exc_info.value.status_code == 404, traversal_id


def test_project_dir_still_works_for_a_real_project(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(paths, "PROJECTS_DIR", tmp_path / "projects")
    project = tmp_path / "projects" / "demo"
    project.mkdir(parents=True)
    (project / "meta.json").write_text(json.dumps({"id": "demo"}), encoding="utf-8")

    resolved = paths.project_dir("demo")
    assert resolved == project.resolve()
