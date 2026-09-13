"""Run a training command, then evaluate only after successful completion.

The wrapper and all children belong to the job's process tree, so Stop also
stops validation, training and evaluation subprocesses.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", required=True, type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("training command required")
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode:
        raise SystemExit(result.returncode)
    print("\nTRAINING COMPLETE — starting automatic evaluation", flush=True)
    result = subprocess.run([sys.executable, str(ROOT / "evaluation/run.py"),
                             "--project-dir", str(args.project_dir)], cwd=ROOT)
    if result.returncode:
        print("Training completed, but evaluation failed. The adapter is still saved.", flush=True)
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
