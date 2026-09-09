"""Merge a LoRA adapter into the base model, producing a standalone HF model
(no PEFT dependency needed to load it) for export to GGUF/Ollama.

Loads the base model in bf16 (not 4-bit) — merging requires full-precision
weights, QLoRA's 4-bit base is only for training memory savings.

Usage:
    python scripts/merge_adapter.py --adapter experiment_003 --output models/merged/experiment_003
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = Path(__file__).resolve().parent.parent
MODEL_NAME = "unsloth/Llama-3.2-1B-Instruct"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", required=True, help="experiment id, e.g. experiment_003")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    adapter_path = ROOT / "models" / "adapters" / args.adapter
    if not adapter_path.exists():
        raise SystemExit(f"no adapter at {adapter_path}")

    output_dir = args.output or (ROOT / "models" / "merged" / args.adapter)
    if output_dir.exists() and any(output_dir.iterdir()):
        raise SystemExit(f"{output_dir} already exists and is non-empty — remove it first if you want to re-merge")
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[1/4] loading base model in bf16: {MODEL_NAME}")
    base = AutoModelForCausalLM.from_pretrained(MODEL_NAME, dtype=torch.bfloat16, device_map={"": 0})

    print(f"[2/4] loading adapter: {adapter_path}")
    model = PeftModel.from_pretrained(base, str(adapter_path))

    print("[3/4] merging adapter into base weights")
    merged = model.merge_and_unload()

    print(f"[4/4] saving merged model to {output_dir}")
    merged.save_pretrained(str(output_dir), safe_serialization=True)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    tokenizer.save_pretrained(str(output_dir))

    _fix_tokenizer_class(output_dir)

    print("Done.")


def _fix_tokenizer_class(output_dir: Path) -> None:
    """transformers 5.15.0 (bleeding-edge) saves tokenizer_class as the internal
    "TokenizersBackend" name, which AutoTokenizer.from_pretrained (used by the
    GGUF converter) doesn't recognize. Patch the label back to the standard
    "PreTrainedTokenizerFast" — same tokenizer behavior, just a correct class name."""
    config_path = output_dir / "tokenizer_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("tokenizer_class") == "TokenizersBackend":
        config["tokenizer_class"] = "PreTrainedTokenizerFast"
        config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
