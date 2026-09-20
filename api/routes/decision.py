"""Decision Model endpoints, scoped to one project (mission §2-§9).

Nested under /api/projects/{project_id}/decision/... — not the mission's literal
POST /v1/decisions/{model} — so every route inherits the same project-role
enforcement every other project-scoped route gets for free from the
observability_and_audit middleware in api/main.py (viewer for GET, operator for
mutating verbs). A standalone /v1/decisions/{model} path would bypass that
check entirely (mission §17: "aucun accès direct à une action critique sans
policy explicite"). /api/v1/projects/{id}/decision/infer is available too, via
the existing ApiV1AliasMiddleware.

Route order matters (see api/routes/dataset.py's note): static-looking
sub-paths like "schema", "validate", "stats", "evaluate", "infer", "fallback"
are declared as their own routes, not swallowed by a catch-all.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request

from api.enterprise import actor_from_request, store
from api.paths import project_dir
from api.schemas import (
    AddDecisionExampleRequest,
    DecisionDatasetStats,
    DecisionEvaluationResult,
    DecisionExample,
    DecisionFallbackConfig,
    DecisionRequest,
    DecisionResult,
    DecisionSchema,
    DecisionValidationResult,
    UpdateDecisionExampleRequest,
)
from api.storage import atomic_write_text
from decision import dataset as decision_dataset
from decision import gateway, schema_store
from decision import metrics as decision_metrics

router = APIRouter(prefix="/api/projects/{project_id}/decision", tags=["decision"])


@router.get("/schema", response_model=DecisionSchema | None)
def get_schema(project: Path = Depends(project_dir)):
    return schema_store.load_schema(project)


@router.put("/schema", response_model=DecisionSchema)
def put_schema(body: DecisionSchema, project: Path = Depends(project_dir)):
    return schema_store.save_schema(project, body)


@router.get("/dataset/validate", response_model=DecisionValidationResult)
def validate_dataset(project: Path = Depends(project_dir)):
    schema = schema_store.require_schema(project)
    return decision_dataset.validate(project, schema)


@router.get("/dataset/stats", response_model=DecisionDatasetStats)
def dataset_stats(project: Path = Depends(project_dir)):
    return decision_dataset.stats(project)


@router.get("/dataset/{split}", response_model=list[DecisionExample])
def list_examples(split: str, project: Path = Depends(project_dir)):
    if split not in decision_dataset.SPLITS:
        raise HTTPException(400, f"split doit etre parmi {decision_dataset.SPLITS}")
    return decision_dataset.read_split(project, split)


@router.post("/dataset", response_model=DecisionExample)
def add_example(body: AddDecisionExampleRequest, project: Path = Depends(project_dir)):
    split = body.file.removesuffix(".jsonl")
    return decision_dataset.append_example(project, split, body.input, body.decision)


@router.put("/dataset/{split}/{index}", response_model=DecisionExample)
def update_example(body: UpdateDecisionExampleRequest, split: str, index: int, project: Path = Depends(project_dir)):
    if split not in decision_dataset.SPLITS:
        raise HTTPException(400, f"split doit etre parmi {decision_dataset.SPLITS}")
    try:
        return decision_dataset.update_example(project, split, index, body.input, body.decision)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.delete("/dataset/{split}/{index}")
def delete_example(split: str, index: int, project: Path = Depends(project_dir)):
    if split not in decision_dataset.SPLITS:
        raise HTTPException(400, f"split doit etre parmi {decision_dataset.SPLITS}")
    try:
        decision_dataset.delete_example(project, split, index)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"deleted": True}


@router.post("/evaluate", response_model=DecisionEvaluationResult)
def evaluate(request: Request, project_id: str, project: Path = Depends(project_dir)):
    """Runs the project's active model against decision/dataset/test.jsonl and
    records the result as a draft registry entry, keyed by timestamp, with the
    metrics in `artifacts` (mission §6/§11) — reuses the existing
    model_versions/artifacts_json blob instead of a second results store."""
    schema = schema_store.require_schema(project)
    examples = decision_dataset.read_split(project, "test")
    if not examples:
        raise HTTPException(409, "decision/dataset/test.jsonl est vide — ajoutez des exemples de test avant d'evaluer")

    pairs: list[tuple[str, str]] = []
    latencies: list[float] = []
    for example in examples:
        started = datetime.now(UTC)
        try:
            decision, _confidence = gateway._run_once(project, project_id, schema, example.input)
        except gateway.DecisionError:
            decision = decision_metrics.INVALID
        latencies.append((datetime.now(UTC) - started).total_seconds() * 1000)
        pairs.append((example.decision, decision))

    result = decision_metrics.evaluate(pairs, schema.decisions, latencies)

    actor = actor_from_request(request)
    version_label = f"decision-eval-{result.generated_at}"
    store.create_version(
        project_id, version_label, model=project_id, dataset_version=None,
        benchmark_at=result.generated_at, actor=actor, notes="Decision Model evaluation",
        artifacts={"decision_evaluation": result.model_dump(), "decision_schema": schema.model_dump()},
    )
    return result


@router.get("/fallback", response_model=DecisionFallbackConfig)
def get_fallback(project: Path = Depends(project_dir)):
    path = project / "decision" / "fallback.json"
    if not path.exists():
        return DecisionFallbackConfig()
    return DecisionFallbackConfig.model_validate_json(path.read_text(encoding="utf-8"))


@router.put("/fallback", response_model=DecisionFallbackConfig)
def put_fallback(body: DecisionFallbackConfig, project: Path = Depends(project_dir)):
    (project / "decision").mkdir(parents=True, exist_ok=True)
    atomic_write_text(project / "decision" / "fallback.json", json.dumps(body.model_dump(), ensure_ascii=False, indent=2) + "\n")
    return body


@router.post("/infer", response_model=DecisionResult)
def infer(body: DecisionRequest, project_id: str, project: Path = Depends(project_dir)):
    """The Decision Gateway (mission §8): validates input, runs the model,
    validates output, measures latency, records confidence/fallback."""
    fallback = get_fallback(project)
    try:
        result = gateway.decide(
            project_id, body.input,
            fallback_project_id=fallback.fallback_project_id if fallback.enabled else None,
            fallback_threshold=fallback.threshold,
        )
    except gateway.DecisionError as exc:
        raise HTTPException(422, f"decision invalide: {exc}") from exc
    return result
