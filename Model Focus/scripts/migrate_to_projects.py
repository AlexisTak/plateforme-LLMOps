"""One-time migration: move the original flat layout into projects/biscuits-focus/,
the project's new fully-isolated home. Safe to re-run only if projects/biscuits-focus/
doesn't already exist — refuses otherwise rather than silently merging/overwriting.

Usage:
    python scripts/migrate_to_projects.py
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECT_ID = "biscuits-focus"
PROJECT_DIR = ROOT / "projects" / PROJECT_ID

MOVES = [
    ("datasets", "datasets"),
    ("data", "data"),
    ("rag/documents", "rag/documents"),
    ("rag/index", "rag/index"),
    ("rag/chunks", "rag/chunks"),
    ("training/configs", "training/configs"),
    ("experiments", "experiments"),
    ("models/adapters", "models/adapters"),
    ("models/merged", "models/merged"),
    ("models/quantized", "models/quantized"),
]


def main() -> None:
    if PROJECT_DIR.exists():
        raise SystemExit(f"{PROJECT_DIR} already exists — refusing to migrate again.")

    profiles_path = ROOT / "models" / "profiles.json"
    if profiles_path.exists():
        profiles = json.loads(profiles_path.read_text(encoding="utf-8"))
        first = profiles[0]
        base_model = first["id"]
        label = "Biscuits Focus (Llama 3.2 1B)"
        ollama_equivalent = first.get("ollama_equivalent")
        added_at = first.get("added_at", datetime.now(timezone.utc).isoformat())
    else:
        base_model = "unsloth/Llama-3.2-1B-Instruct"
        label = "Biscuits Focus (Llama 3.2 1B)"
        ollama_equivalent = "llama3.2:1b"
        added_at = datetime.now(timezone.utc).isoformat()

    PROJECT_DIR.mkdir(parents=True)

    for src_rel, dst_rel in MOVES:
        src = ROOT / src_rel
        dst = PROJECT_DIR / dst_rel
        if not src.exists():
            print(f"skip (missing): {src_rel}")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        print(f"moved: {src_rel} -> projects/{PROJECT_ID}/{dst_rel}")

    eval_dst = PROJECT_DIR / "evaluation"
    eval_dst.mkdir(parents=True, exist_ok=True)
    for name in ("benchmark.jsonl", "report.md", "report_summary.json"):
        src = ROOT / "evaluation" / name
        if src.exists():
            shutil.move(str(src), str(eval_dst / name))
            print(f"moved: evaluation/{name} -> projects/{PROJECT_ID}/evaluation/{name}")

    meta = {
        "id": PROJECT_ID,
        "base_model": base_model,
        "label": label,
        "ollama_equivalent": ollama_equivalent,
        "added_at": added_at,
    }
    (PROJECT_DIR / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {PROJECT_DIR / 'meta.json'}")

    if profiles_path.exists():
        profiles_path.unlink()
        print("removed models/profiles.json (superseded by projects/<id>/meta.json)")

    print(f"\nMigration complete. Project '{PROJECT_ID}' is now at {PROJECT_DIR}")


if __name__ == "__main__":
    main()
