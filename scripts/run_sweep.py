"""Full LoRA rank sweep: runs the validate -> prepare -> train pipeline for
r=8, r=16 and r=32 back-to-back, one job. Unlike scripts/run_pipeline.py this
keeps going if one config fails (so you still get results for the others) and
prints a pass/fail summary at the end. Same as always: only touches
datasets/ / data/ / training/ / models/adapters/ — never rag/documents/.

Usage:
    python scripts/run_sweep.py --dataset-version dataset-v0.4
    python scripts/run_sweep.py --dataset-version dataset-v0.4 --resume
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
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    results: dict[str, bool] = {}

    for config_filename in SWEEP_CONFIGS:
        print(f"\n########## SWEEP: {config_filename} ##########")
        cmd = [
            PYTHON,
            str(ROOT / "scripts/run_pipeline.py"),
            "--config",
            f"training/configs/{config_filename}",
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
