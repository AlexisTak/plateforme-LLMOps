"""Reads/writes the one DecisionSchema a decision project has, at
projects/<id>/decision/schema.json — mirrors api/paths.py's "one file, one
project-relative path" convention used everywhere else in the codebase."""

from __future__ import annotations

import json
from pathlib import Path

from api.schemas import DecisionSchema
from api.storage import atomic_write_text


def schema_path(project_dir: Path) -> Path:
    return project_dir / "decision" / "schema.json"


def load_schema(project_dir: Path) -> DecisionSchema | None:
    path = schema_path(project_dir)
    if not path.exists():
        return None
    return DecisionSchema.model_validate_json(path.read_text(encoding="utf-8"))


def save_schema(project_dir: Path, schema: DecisionSchema) -> DecisionSchema:
    path = schema_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(schema.model_dump(), indent=2, ensure_ascii=False) + "\n")
    return schema


def require_schema(project_dir: Path) -> DecisionSchema:
    schema = load_schema(project_dir)
    if schema is None:
        from fastapi import HTTPException

        raise HTTPException(409, "Aucun decision schema defini pour ce projet — creez-en un avant de continuer")
    return schema
