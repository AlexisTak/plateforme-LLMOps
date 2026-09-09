"""Generate a Modelfile and create an Ollama model from a merged HF model
(mission section 34). Uses Ollama's `--experimental` safetensors import +
built-in `--quantize`, so no local llama.cpp build is needed.

Usage:
    python scripts/build_ollama_model.py --merged models/merged/experiment_003 --name biscuits-focus --quantize q4_K_M
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SYSTEM_PROMPT_PATH = ROOT / "training/configs/system_prompt.txt"


def build_modelfile(merged_dir: Path, temperature: float) -> str:
    system_prompt = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
    # Modelfile SYSTEM uses a triple-quoted string — escape any literal triple-quotes (none expected here).
    return f'''FROM {merged_dir.resolve()}
SYSTEM """{system_prompt}"""
PARAMETER temperature {temperature}
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--merged", type=Path, required=True, help="path to a merged HF model dir (scripts/merge_adapter.py output)")
    parser.add_argument("--name", required=True, help="Ollama model name, e.g. biscuits-focus-q4")
    parser.add_argument("--quantize", default=None, help="e.g. q4_K_M, q5_K_M, q8_0 — omit to keep full precision")
    parser.add_argument("--temperature", type=float, default=0.3)
    args = parser.parse_args()

    if not args.merged.exists():
        raise SystemExit(f"no merged model at {args.merged}")

    modelfile_content = build_modelfile(args.merged, args.temperature)
    modelfile_path = args.merged / "Modelfile"
    modelfile_path.write_text(modelfile_content, encoding="utf-8")
    print(f"Modelfile written to {modelfile_path}:\n{modelfile_content}")

    cmd = ["ollama", "create", args.name, "-f", str(modelfile_path), "--experimental"]
    if args.quantize:
        cmd += ["-q", args.quantize]

    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    print(f"\nDone — try: ollama run {args.name}")


if __name__ == "__main__":
    main()
