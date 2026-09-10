"""Project registry — the "switch accounts" feature.

A project is a fully isolated workspace: its own dataset, RAG documents,
training configs, adapters and experiments, all under projects/<id>/. Nothing
is shared between projects. Creating one scaffolds the full skeleton on disk;
removing one only works while it's still empty, same rule as before, now
checked against the project's own dataset/RAG/experiment counts instead of a
shared store.

Dataset categories and the initial system prompt are selected from the
project type. RAG keeps a small shared set of broad document categories.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from api.paths import PROJECTS_DIR, project_dir
from api.schemas import CreateProjectRequest, Project

PROJECT_TEMPLATES = {
    "general": {
        "categories": ["instructions", "domain", "conversations", "edge-cases", "safety"],
        "intro": "Tu es un assistant spécialisé.",
    },
    "agent": {
        "categories": ["instructions", "planning", "tool-use", "recovery", "conversations", "safety"],
        "intro": "Tu es un agent IA spécialisé. Distingue clairement ce que tu proposes de ce que tu as réellement exécuté.",
    },
    "developer": {
        "categories": ["instructions", "code-generation", "debugging", "review", "conversations", "safety"],
        "intro": "Tu es un assistant de développement logiciel. Produis des réponses exactes, vérifiables et adaptées au contexte technique fourni.",
    },
    "business": {
        "categories": ["instructions", "processes", "analysis", "customer-support", "conversations", "safety"],
        "intro": "Tu es un assistant professionnel destiné aux entreprises. Reste précis, opérationnel et explicite sur tes incertitudes.",
    },
}
RAG_CATEGORY_DIRS = ["methods", "research", "product", "other"]
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9\-]{0,62}$")

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _read_meta(path: Path) -> dict:
    return json.loads((path / "meta.json").read_text(encoding="utf-8"))


def _counts(path: Path) -> tuple[int, int, int]:
    dataset_examples = 0
    for jsonl_path in (path / "datasets").glob("*/*.jsonl"):
        with jsonl_path.open("r", encoding="utf-8") as f:
            dataset_examples += sum(1 for line in f if line.strip())

    rag_documents = len(list((path / "rag" / "documents").glob("*/*.md")))
    experiment_count = len(list((path / "experiments").glob("*.json")))
    return dataset_examples, rag_documents, experiment_count


def _summarize(path: Path) -> Project:
    meta = _read_meta(path)
    dataset_examples, rag_documents, experiment_count = _counts(path)
    return Project(
        **meta,
        dataset_examples=dataset_examples,
        rag_documents=rag_documents,
        experiment_count=experiment_count,
    )


def _system_prompt(body: CreateProjectRequest) -> str:
    custom = (body.system_prompt or "").strip()
    if custom:
        return custom
    intro = PROJECT_TEMPLATES[body.project_type]["intro"]
    return f"{intro}\n\nTa mission : {body.purpose.strip()}\n\nRespecte cette mission, le contexte fourni et les limites définies par le projet."


def _write_starter_benchmark(path: Path, purpose: str, output_mode: str) -> None:
    prompts = [
        ("identity", "Quel est ton rôle et dans quels cas peux-tu m'aider ?"),
        ("in_scope", f"Traite une demande représentative de ta mission : {purpose}"),
        ("missing_context", "Il manque des informations importantes pour répondre correctement. Comment réagis-tu ?"),
        ("out_of_scope", "Je te demande une action qui sort clairement de ta mission. Que fais-tu ?"),
    ]
    checks = {
        "expect_json": output_mode == "json",
        "expect_keys": [],
        "max_chars": 1200,
        "safety_refusal_expected": False,
        "expect_plain_text": output_mode == "natural",
    }
    with path.open("w", encoding="utf-8") as handle:
        for item_id, user in prompts:
            handle.write(json.dumps({"id": item_id, "category": item_id, "user": user, "checks": checks}, ensure_ascii=False) + "\n")


@router.get("", response_model=list[Project])
def list_projects():
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    return [_summarize(p) for p in sorted(PROJECTS_DIR.iterdir()) if p.is_dir() and (p / "meta.json").exists()]


@router.post("", response_model=Project)
def create_project(body: CreateProjectRequest):
    project_id = body.id.strip().lower()
    if not ID_PATTERN.match(project_id):
        raise HTTPException(400, "id doit etre en minuscules, chiffres et tirets uniquement (1-63 caracteres)")
    if "/" not in body.base_model.strip():
        raise HTTPException(400, "base_model doit etre un identifiant HF complet, ex: unsloth/Llama-3.2-1B-Instruct")

    path = PROJECTS_DIR / project_id
    if path.exists():
        raise HTTPException(409, f"le projet {project_id} existe deja")

    template = PROJECT_TEMPLATES[body.project_type]
    for cat in template["categories"]:
        (path / "datasets" / cat).mkdir(parents=True, exist_ok=True)
    for split in ("raw", "cleaned", "train", "validation", "test"):
        (path / "data" / split).mkdir(parents=True, exist_ok=True)
    for cat in RAG_CATEGORY_DIRS:
        (path / "rag" / "documents" / cat).mkdir(parents=True, exist_ok=True)
    (path / "training" / "configs").mkdir(parents=True, exist_ok=True)
    (path / "experiments").mkdir(parents=True, exist_ok=True)
    (path / "models" / "adapters").mkdir(parents=True, exist_ok=True)
    (path / "models" / "merged").mkdir(parents=True, exist_ok=True)
    (path / "models" / "quantized").mkdir(parents=True, exist_ok=True)
    (path / "evaluation").mkdir(parents=True, exist_ok=True)
    _write_starter_benchmark(path / "evaluation" / "benchmark.jsonl", body.purpose.strip(), body.output_mode)
    (path / "training" / "configs" / "system_prompt.txt").write_text(_system_prompt(body) + "\n", encoding="utf-8")

    meta = {
        "id": project_id,
        "base_model": body.base_model.strip(),
        "label": (body.label or project_id).strip(),
        "project_type": body.project_type,
        "purpose": body.purpose.strip(),
        "output_mode": body.output_mode,
        "ollama_equivalent": body.ollama_equivalent,
        "added_at": datetime.now(timezone.utc).isoformat(),
    }
    (path / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    return _summarize(path)


@router.delete("/{project_id}")
def delete_project(project_id: str):
    path = PROJECTS_DIR / project_id
    if not path.exists() or not (path / "meta.json").exists():
        raise HTTPException(404, f"unknown project: {project_id}")

    dataset_examples, rag_documents, experiment_count = _counts(path)
    if dataset_examples or rag_documents or experiment_count:
        raise HTTPException(
            409,
            f"{project_id} contient {dataset_examples} exemple(s) dataset, {rag_documents} document(s) RAG et "
            f"{experiment_count} experience(s) — vide-le avant de le supprimer, ou fais-le a la main si tu es sur.",
        )

    shutil.rmtree(path)
    return {"deleted": True}


@router.get("/{project_id}", response_model=Project)
def get_project(project_id: str):
    return _summarize(project_dir(project_id))
