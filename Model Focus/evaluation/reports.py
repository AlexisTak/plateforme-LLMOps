"""Versioned evaluation artifacts, provenance and comparable metric deltas."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from api.storage import atomic_write_text

SCORING_VERSION = "human-rubric-v2"


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
        "generated_at": datetime.now(timezone.utc).isoformat(),
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
    if comparable:
        for label, metrics in summary.items():
            old = previous.get("summary", {}).get(label, {})
            if old.get("n") != metrics.get("n"):
                continue
            deltas[label] = {key: round(value - old[key], 1) for key, value in metrics.items()
                             if key.endswith("_pct") and value is not None and old.get(key) is not None}
    return {"comparable": bool(comparable), "previous_generated_at": old_meta.get("generated_at"), "deltas": deltas}


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
        archive = history / f"previous-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}.json"
        archive.write_text(json.dumps(previous, ensure_ascii=False, indent=2), encoding="utf-8")
    for target, content in ((directory / "report.md", markdown),
                            (path, json.dumps(report, ensure_ascii=False, indent=2))):
        atomic_write_text(target, content)
    return report
