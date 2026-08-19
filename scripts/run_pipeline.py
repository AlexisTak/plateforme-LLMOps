"""Autonomous fine-tuning pipeline: validate -> prepare splits -> train.

Chains the existing single-purpose scripts (each already usable standalone)
so a full run can be launched from the web console as one background job and
finishes on its own without further clicks. Fails fast on validation errors —
never trains on a dataset that doesn't pass scripts/validate_dataset.py.

Operates only on datasets/ -> data/ -> training/ (fine-tuning). Never touches
rag/documents/ — RAG and fine-tuning stay separate pipelines by design, see
README.md "Trois systèmes séparés".

Usage:
    python scripts/run_pipeline.py --config training/configs/lora_r32.yaml --dataset-version dataset-v0.4
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


def run_step(name: str, cmd: list[str]) -> None:
    print(f"\n===== STEP: {name} =====")
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        print(f"\nPIPELINE FAILED at step: {name} (exit code {result.returncode})")
        raise SystemExit(result.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", required=True, type=Path, help="e.g. projects/biscuits-focus")
    parser.add_argument("--config", required=True, help="path to a *.yaml config, e.g. projects/biscuits-focus/training/configs/lora_r32.yaml")
    parser.add_argument("--dataset-version", required=True, help="e.g. dataset-v0.4")
    parser.add_argument("--resume", action="store_true", help="passed through to train.py")
    args = parser.parse_args()

    config_path = Path(args.config)
    project_dir = args.project_dir
    datasets_glob = str(project_dir / "datasets" / "**" / "*.jsonl")
    train_glob = str(project_dir / "data" / "train" / "*.jsonl")
    val_glob = str(project_dir / "data" / "validation" / "*.jsonl")
    test_glob = str(project_dir / "data" / "test" / "*.jsonl")

    run_step(
        "validate raw dataset (datasets/)",
        [PYTHON, "scripts/validate_dataset.py", datasets_glob],
    )

    run_step(
        "prepare splits (data/train, data/validation, data/test)",
        [PYTHON, "scripts/prepare_dataset.py", "--project-dir", str(project_dir), "--dataset-version", args.dataset_version],
    )

    run_step(
        "validate splits + check train/test leakage",
        [PYTHON, "scripts/validate_dataset.py", train_glob, val_glob, test_glob, "--check-leakage"],
    )

    train_cmd = [PYTHON, "training/scripts/train.py", "--project-dir", str(project_dir), "--config", str(config_path)]
    if args.resume:
        train_cmd.append("--resume")
    run_step("train", train_cmd)

    print("\nPIPELINE COMPLETE.")


if __name__ == "__main__":
    main()
