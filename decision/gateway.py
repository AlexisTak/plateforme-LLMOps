"""Decision Gateway (mission §8/§9) — loads the active model, validates the
input, runs generation constrained to the project's DecisionSchema, validates
the output, measures latency, and optionally falls back to another project's
model when confidence is too low.

Stays on the existing CAUSAL_LM LoRA/QLoRA pipeline: a Decision Model is a
*generation* model fine-tuned to always emit `{"decision": ..., "confidence": ...}`
— no separate classification-head training path (see docs/DECISION_MODELS.md
for why: it reuses the training engine as-is per mission §22 "ne duplique pas
le moteur de training").
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from api.model_manager import manager
from api.paths import project_dir as resolve_project_dir
from api.schemas import DecisionResult, DecisionSchema

from . import schema_store


class DecisionError(ValueError):
    """Raised when the model's output does not satisfy the DecisionSchema —
    mission §3: "Une décision invalide doit être considérée comme une erreur
    de modèle et non comme une réponse valide."."""


def _build_prompt(schema: DecisionSchema) -> str:
    options = ", ".join(f'"{d}"' for d in schema.decisions)
    confidence_line = ' et "confidence" (nombre entre 0 et 1)' if schema.confidence else ""
    return (
        f"Tu es le modèle de décision \"{schema.name}\". Réponds uniquement avec un objet JSON valide "
        f'contenant la clé "decision" (une valeur parmi [{options}]){confidence_line}. '
        "Aucun texte avant ou après le JSON."
    )


def _parse_and_validate(raw: str, schema: DecisionSchema) -> tuple[str, float | None]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[-1] if "\n" in text else text.strip("`")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DecisionError(f"sortie non-JSON: {exc}") from exc
    if not isinstance(payload, dict) or "decision" not in payload:
        raise DecisionError("cle 'decision' manquante dans la sortie")
    decision = payload["decision"]
    if not isinstance(decision, str) or decision not in schema.decisions:
        raise DecisionError(f"decision '{decision}' hors du schema autorise")
    confidence = payload.get("confidence")
    if confidence is not None:
        if not isinstance(confidence, (int, float)) or not (0 <= float(confidence) <= 1):
            raise DecisionError("confidence doit etre un nombre entre 0 et 1")
        confidence = float(confidence)
    return decision, confidence


def _run_once(project_dir: Path, model_label: str, schema: DecisionSchema, input_text: str) -> tuple[str, float | None]:
    raw = manager.generate(
        project_dir=project_dir,
        message=input_text,
        adapter=None,
        system_prompt=_build_prompt(schema),
        max_new_tokens=120,
    )
    return _parse_and_validate(raw, schema)


def decide(project_id: str, input_text: str, *, fallback_project_id: str | None = None,
           fallback_threshold: float = 0.90) -> DecisionResult:
    """Raises DecisionError if the primary model's output is invalid and no
    usable fallback is configured — an invalid decision must never be
    silently returned as if it were valid (mission §3/§17)."""
    pdir = resolve_project_dir(project_id)
    schema = schema_store.require_schema(pdir)

    started = time.perf_counter()
    decision, confidence = _run_once(pdir, project_id, schema, input_text)
    fallback_used = False

    if fallback_project_id and schema.confidence and confidence is not None and confidence < fallback_threshold:
        fallback_dir = resolve_project_dir(fallback_project_id)
        fallback_schema = schema_store.require_schema(fallback_dir)
        try:
            decision, confidence = _run_once(fallback_dir, fallback_project_id, fallback_schema, input_text)
            fallback_used = True
        except DecisionError:
            pass  # keep the primary (low-confidence but valid) decision rather than fail the request

    latency_ms = (time.perf_counter() - started) * 1000
    return DecisionResult(
        decision=decision, confidence=confidence,
        model=fallback_project_id if fallback_used else project_id,
        latency_ms=round(latency_ms, 2), fallback_used=fallback_used,
    )
