"""Resolves a project id (URL path param) to its directory on disk.

Every project is a fully isolated workspace at projects/<id>/ — its own
datasets/, data/, rag/, training/configs/, experiments/, models/. This module
is the one place that maps id -> Path, used as a FastAPI dependency by every
project-scoped router so no route hardcodes the projects/ layout itself.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

ROOT = Path(__file__).resolve().parent.parent
PROJECTS_DIR = ROOT / "projects"


def project_dir(project_id: str) -> Path:
    path = PROJECTS_DIR / project_id
    if not path.exists() or not (path / "meta.json").exists():
        raise HTTPException(404, f"unknown project: {project_id}")
    return path
