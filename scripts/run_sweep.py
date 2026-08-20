"""Full LoRA rank sweep: runs the validate -> prepare -> train pipeline for
r=8, r=16 and r=32 back-to-back, one job. Unlike scripts/run_pipeline.py this
keeps going if one config fails (so you still get results for the others) and
prints a pass/fail summary at the end. Same as always: only touches
datasets/ / data/ / training/ / models/adapters/ — never rag/documents/.

Usage:
    python scripts/run_sweep.py --project-dir projects/biscuits-focus --dataset-version dataset-v0.4
    python scripts/run_sweep.py --project-dir projects/biscuits-focus --dataset-version dataset-v0.4 --resume

Requires the project to already have lora_r8.yaml / lora_r16.yaml / lora_r32.yaml
under its training/configs/ — these aren't auto-generated for a new project, so
create them first (via /training's "Nouvelle config", named exactly that).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable

SWEEP_CONFIGS = ["lora_r8.yaml", "lora_r16.yaml", "lora_r32.yaml"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", required=True, type=Path, help="e.g. projects/biscuits-focus")
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    project_dir: Path = args.project_dir
    results: dict[str, bool] = {}

    for config_filename in SWEEP_CONFIGS:
        print(f"\n########## SWEEP: {config_filename} ##########")
        config_path = project_dir / "training" / "configs" / config_filename
        if not config_path.exists():
            print(f"########## SWEEP: {config_filename} -> SKIPPED (no such config in this project) ##########")
            results[config_filename] = False
            continue
        cmd = [
            PYTHON,
            str(ROOT / "scripts/run_pipeline.py"),
            "--project-dir",
            str(project_dir),
            "--config",
            str(config_path),
            "--dataset-version",
            args.dataset_version,
        ]
        if args.resume:
            cmd.append("--resume")

        result = subprocess.run(cmd, cwd=str(ROOT))
        ok = result.returncode == 0
        results[config_filename] = ok
        status = "OK" if ok else f"FAILED (exit {result.returncode})"
        print(f"########## SWEEP: {config_filename} -> {status} ##########")

    print("\n===== SWEEP SUMMARY =====")
    for config_filename, ok in results.items():
        print(f"  {'OK  ' if ok else 'FAIL'}  {config_filename}")

    if not all(results.values()):
        raise SystemExit(1)

    print("\nSWEEP COMPLETE — all 3 configs trained successfully.")


if __name__ == "__main__":
    main()
