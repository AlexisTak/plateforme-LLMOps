"""Resolves a project id (URL path param) to its directory on disk.

Every project is a fully isolated workspace at projects/<id>/ — its own
datasets/, data/, rag/, training/configs/, experiments/, models/. This module
is the one place that maps id -> Path, used as a FastAPI dependency by every
project-scoped router so no route hardcodes the projects/ layout itself.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import HTTPException

ROOT = Path(__file__).resolve().parent.parent
PROJECTS_DIR = ROOT / "projects"

# Same charset enforced at creation time (api/routes/projects.py::ID_PATTERN) — every
# real project id is already lowercase alphanumeric/hyphens, so this rejects nothing
# legitimate. Defense in depth: project_id is a raw URL path segment, and this
# dependency is what every project-scoped route joins onto the filesystem.
_SAFE_PROJECT_ID = re.compile(r"^[a-z0-9][a-z0-9\-]{0,62}$")


def project_dir(project_id: str) -> Path:
    if not _SAFE_PROJECT_ID.match(project_id):
        raise HTTPException(404, f"unknown project: {project_id}")
    path = (PROJECTS_DIR / project_id).resolve()
    if PROJECTS_DIR.resolve() not in path.parents or not path.exists() or not (path / "meta.json").exists():
        raise HTTPException(404, f"unknown project: {project_id}")
    return path
