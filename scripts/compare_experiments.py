"""Print a comparison table across experiments/*.json result files.

Usage:
    python scripts/compare_experiments.py
"""

from __future__ import annotations

import json
from pathlib import Path

EXPERIMENTS_DIR = Path(__file__).resolve().parent.parent / "experiments"

COLUMNS = ["experiment_id", "lora.r", "train_loss", "eval_loss", "train_duration_minutes", "peak_vram_mb", "adapter_size_mb"]


def get(d: dict, dotted: str):
    cur = d
    for part in dotted.split("."):
        cur = cur.get(part) if isinstance(cur, dict) else None
        if cur is None:
            return None
    return cur


def main() -> None:
    results = []
    for path in sorted(EXPERIMENTS_DIR.glob("experiment_*.json")):
        results.append(json.loads(path.read_text(encoding="utf-8")))

    if not results:
        print("No experiment result files found in experiments/.")
        return

    widths = {c: max(len(c), *(len(str(get(r, c))) for r in results)) for c in COLUMNS}
    header = " | ".join(c.ljust(widths[c]) for c in COLUMNS)
    print(header)
    print("-" * len(header))
    for r in results:
        print(" | ".join(str(get(r, c)).ljust(widths[c]) for c in COLUMNS))


if __name__ == "__main__":
    main()
