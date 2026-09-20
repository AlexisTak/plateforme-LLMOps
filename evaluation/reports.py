"""Versioned evaluation artifacts, provenance and comparable metric deltas."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from api.storage import atomic_write_text

SCORING_VERSION = "human-rubric-v2"

# CLAUDE.md §11: "une amélioration sur une métrique ne doit pas masquer une
# régression critique sur une autre" — every *_pct axis is checked
# independently, an improvement on one never cancels out a drop on another.
REGRESSION_THRESHOLD_PCT = 5.0
# refusal_rate_pct is the one *_pct metric where higher is worse — a rise, not
# a drop, is the regression.
LOWER_IS_BETTER_PCT_METRICS = {"refusal_rate_pct"}


def _is_regression(metric: str, delta: float) -> bool:
    if metric in LOWER_IS_BETTER_PCT_METRICS:
        return delta > REGRESSION_THRESHOLD_PCT
    return delta < -REGRESSION_THRESHOLD_PCT


def fingerprint(path: Path) -> dict | None:
    if not path.exists():
        return None
    stat = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {"sha256": digest.hexdigest(), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def capture_metadata(project: Path) -> dict:
    files = [project / "evaluation/benchmark.jsonl", project / "training/configs/system_prompt.txt", project / "meta.json"]
    files += sorted((project / "data").glob("*/*.jsonl"))
    files += sorted((project / "models/adapters").glob("*/adapter_config.json"))
    files += sorted((project / "models/adapters").glob("*/adapter_model.safetensors"))
    version = project / "data/VERSION"
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "scoring_version": SCORING_VERSION,
        "dataset_version": version.read_text(encoding="utf-8").strip() if version.exists() else None,
        "files": {str(path.relative_to(project)).replace("\\", "/"): fingerprint(path) for path in files},
    }


def stale_reasons(project: Path, metadata: dict) -> list[str]:
    if not metadata or metadata.get("scoring_version") != SCORING_VERSION:
        return ["Ancien rapport : relancer une évaluation avec les critères texte."]
    reasons = []
    version = project / "data/VERSION"
    current = version.read_text(encoding="utf-8").strip() if version.exists() else None
    if current != metadata.get("dataset_version"):
        reasons.append("La version du dataset a changé.")
    for name, recorded in metadata.get("files", {}).items():
        path = project / name
        if not path.exists():
            if recorded is not None:
                reasons.append(f"Fichier supprimé : {name}")
        elif recorded is None or (path.stat().st_size, path.stat().st_mtime_ns) != (recorded["size"], recorded["mtime_ns"]):
            reasons.append(f"Fichier modifié : {name}")
    current_files = {str(p.relative_to(project)).replace("\\", "/") for pattern in
                     ("models/adapters/*/adapter_config.json", "models/adapters/*/adapter_model.safetensors", "data/*/*.jsonl")
                     for p in project.glob(pattern)}
    if current_files - metadata.get("files", {}).keys():
        reasons.append("Des données ou adapters ont été ajoutés depuis l'évaluation.")
    return reasons


def comparison(previous: dict, metadata: dict, summary: dict) -> dict:
    old_meta = previous.get("metadata", {})
    comparable = old_meta.get("scoring_version") == metadata["scoring_version"]
    # A different benchmark or system instruction makes a percentage delta misleading.
    for name in ("evaluation/benchmark.jsonl", "training/configs/system_prompt.txt", "meta.json"):
        old = old_meta.get("files", {}).get(name) or {}
        new = metadata["files"].get(name) or {}
        comparable = comparable and old.get("sha256") == new.get("sha256")
    deltas = {}
    regressions = []
    if comparable:
        for label, metrics in summary.items():
            old = previous.get("summary", {}).get(label, {})
            if old.get("n") != metrics.get("n"):
                continue
            label_deltas = {}
            for key, value in metrics.items():
                if key.endswith("_pct") and value is not None and old.get(key) is not None:
                    delta = round(value - old[key], 1)
                    label_deltas[key] = delta
                    if _is_regression(key, delta):
                        regressions.append({"variant": label, "metric": key, "delta": delta})
            old_latency, new_latency = old.get("latency_ms_mean"), metrics.get("latency_ms_mean")
            if old_latency and new_latency is not None:
                latency_delta_pct = round(100 * (new_latency - old_latency) / old_latency, 1)
                label_deltas["latency_ms_mean_delta_pct"] = latency_delta_pct
                if latency_delta_pct > REGRESSION_THRESHOLD_PCT * 2:  # latency tolerates more noise than a rubric score
                    regressions.append({"variant": label, "metric": "latency_ms_mean", "delta_pct": latency_delta_pct})
            deltas[label] = label_deltas
    return {
        "comparable": bool(comparable),
        "previous_generated_at": old_meta.get("generated_at"),
        "deltas": deltas,
        "regressions": regressions,
    }


def save_report(project: Path, metadata: dict, summary: dict, outputs: dict, markdown: str) -> dict:
    directory = project / "evaluation"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "report_summary.json"
    previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    report = {"metadata": metadata, "summary": summary, "outputs": outputs,
              "comparison": comparison(previous, metadata, summary)}
    history = directory / "history"
    history.mkdir(exist_ok=True)
    if previous:
        archive = history / f"previous-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}.json"
        archive.write_text(json.dumps(previous, ensure_ascii=False, indent=2), encoding="utf-8")
    for target, content in ((directory / "report.md", markdown),
                            (path, json.dumps(report, ensure_ascii=False, indent=2))):
        atomic_write_text(target, content)
    return report
