"""Real training entrypoint — config-driven, one YAML file fully describes a run.

Run the smoke test (training/scripts/smoke_test.py) first if you haven't
already (mission rule 48). This script:

- is fully driven by a YAML config (training/configs/*.yaml) — no hardcoded hyperparameters
- sets a seed for reproducibility
- logs to console + a per-run JSON log file
- never overwrites an existing run's output_dir by default (use --resume to clear it and retrain fresh)
- evaluates on the validation split during training
- saves the LoRA adapter (not a merged model) to output_dir
- records a result summary into experiments/<experiment_id>.json for comparison across runs

Usage:
    python training/scripts/train.py --config training/configs/lora_r16.yaml
    python training/scripts/train.py --config training/configs/lora_r16.yaml --resume
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from pathlib import Path

import torch
import yaml
from datasets import load_dataset
from peft import LoraConfig
from transformers import AutoTokenizer, BitsAndBytesConfig, TrainerCallback
from trl import SFTConfig, SFTTrainer

ROOT = Path(__file__).resolve().parent.parent.parent


class JsonlLoggerCallback(TrainerCallback):
    """Append every trainer log_history entry to a per-run JSONL log file."""

    def __init__(self, log_path: Path):
        self.log_path = log_path

    def on_log(self, args, state, control, logs=None, **kwargs):
        if logs is None:
            return
        entry = {"step": state.global_step, "epoch": state.epoch, **logs}
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def current_git_commit() -> str | None:
    """Best-effort — provenance is nice-to-have, never a reason to fail a training run."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=5, check=True,
        )
        return result.stdout.strip()
    except Exception:
        return None


def build_dataset(path: Path):
    files = sorted(str(p) for p in path.glob("*.jsonl"))
    if not files:
        raise FileNotFoundError(f"no .jsonl files found in {path} — run scripts/prepare_dataset.py first")
    return load_dataset("json", data_files=files, split="train")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", required=True, type=Path, help="e.g. projects/biscuits-focus")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="allow retraining into a non-empty output_dir by clearing it first, instead of failing (mission rule 23)",
    )
    args = parser.parse_args()

    project_dir: Path = args.project_dir
    experiments_dir = project_dir / "experiments"
    data_version_path = project_dir / "data" / "VERSION"

    cfg = load_config(args.config)
    experiment_id = cfg["experiment"]["id"]
    output_dir = project_dir / cfg["training"]["output_dir"]

    if output_dir.exists() and any(output_dir.iterdir()):
        if not args.resume:
            raise SystemExit(
                f"{output_dir} already exists and is non-empty. Refusing to overwrite a previous run "
                f"(mission rule 23). Use --resume to clear it and retrain, or change training.output_dir / bump the experiment id in {args.config}."
            )
        # HF Trainer saves a final checkpoint-<step>/ at the end of a completed run, not just
        # mid-training — a "completed" checkpoint has global_step already at the max, so
        # resume_from_checkpoint on it does 0 further steps (nothing looks wrong, eval_loss is
        # just identical to the old run, and it's easy to miss). Runs here take ~1 minute, so
        # there's no real crash-recovery use case worth the complexity of distinguishing a
        # mid-training checkpoint from a finished one — --resume always means "clear and retrain".
        print(f"{output_dir} already has a previous run — clearing it before training fresh (--resume).")
        shutil.rmtree(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    log_path = output_dir / "train_log.jsonl"

    torch.manual_seed(cfg["training"]["seed"])

    print(f"[1/5] loading tokenizer + base model: {cfg['model']['name']}")
    tokenizer = AutoTokenizer.from_pretrained(cfg["model"]["name"])
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    q = cfg["quantization"]
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=q["load_in_4bit"],
        bnb_4bit_quant_type=q["bnb_4bit_quant_type"],
        bnb_4bit_compute_dtype=getattr(torch, q["bnb_4bit_compute_dtype"]),
        bnb_4bit_use_double_quant=q["bnb_4bit_use_double_quant"],
    )

    lora_cfg = cfg["lora"]
    peft_config = LoraConfig(
        r=lora_cfg["r"],
        lora_alpha=lora_cfg["alpha"],
        lora_dropout=lora_cfg["dropout"],
        target_modules=lora_cfg["target_modules"],
        bias=lora_cfg["bias"],
        task_type=lora_cfg["task_type"],
    )

    print("[2/5] loading train/validation datasets")
    train_dataset = build_dataset(project_dir / cfg["dataset"]["train_path"])
    eval_dataset = None
    val_path = project_dir / cfg["dataset"]["validation_path"]
    if val_path.exists() and any(val_path.glob("*.jsonl")):
        eval_dataset = build_dataset(val_path)
    print(f"    train examples: {len(train_dataset)}, validation examples: {len(eval_dataset) if eval_dataset else 0}")

    t = cfg["training"]
    sft_config = SFTConfig(
        output_dir=str(output_dir),
        seed=t["seed"],
        num_train_epochs=t["epochs"],
        learning_rate=t["learning_rate"],
        per_device_train_batch_size=t["batch_size"],
        gradient_accumulation_steps=t["gradient_accumulation_steps"],
        warmup_steps=t["warmup_steps"],
        logging_steps=t["logging_steps"],
        save_steps=t["save_steps"],
        eval_strategy=t["eval_strategy"] if eval_dataset is not None else "no",
        eval_steps=t["eval_steps"] if eval_dataset is not None else None,
        max_length=cfg["dataset"]["max_seq_length"],
        # assistant_only_loss=True would mask user-turn tokens out of the loss, but it requires
        # `{% generation %}` markers in the tokenizer's chat template — the base Llama 3 template
        # doesn't have them and TRL can't auto-patch it. Loss is computed over the full sequence
        # (user + assistant) for now. Revisit with a custom chat template once behavior needs it —
        # low-impact today since examples are short, mostly single-turn.
        assistant_only_loss=False,
        bf16=True,
        report_to=[],
        # Optional, off by default (preserves existing configs' memory profile
        # unchanged) — trades compute for activation memory. Needed for a 7B
        # QLoRA run on an 8GB card; a 1B run never needed it.
        gradient_checkpointing=t.get("gradient_checkpointing", False),
    )

    print("[3/5] building trainer")
    trainer = SFTTrainer(
        model=cfg["model"]["name"],
        args=sft_config,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        processing_class=tokenizer,
        quantization_config=bnb_config,
        peft_config=peft_config,
        callbacks=[JsonlLoggerCallback(log_path)],
    )

    print(f"[4/5] training — logs streaming to {log_path}")
    start = time.time()
    train_result = trainer.train()
    duration_minutes = (time.time() - start) / 60

    print(f"[5/5] saving final adapter to {output_dir}")
    trainer.save_model(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))

    eval_metrics = trainer.evaluate() if eval_dataset is not None else {}
    peak_vram_mb = torch.cuda.max_memory_allocated() / (1024 * 1024) if torch.cuda.is_available() else None
    adapter_size_mb = sum(f.stat().st_size for f in output_dir.glob("*.safetensors")) / (1024 * 1024)

    experiments_dir.mkdir(exist_ok=True)
    result = {
        "experiment_id": experiment_id,
        "config_path": str(args.config),
        "notes": cfg["experiment"].get("notes", ""),
        # data/VERSION is the ground truth of what's actually in data/train right now —
        # the config's dataset.version field is a static label that goes stale as soon
        # as someone reruns scripts/prepare_dataset.py with a different version without
        # also hand-editing every config (this bit us: a sweep trained on dataset-v0.4
        # but every result still said dataset-v0.3 because the yaml was never updated).
        "dataset_version": data_version_path.read_text(encoding="utf-8").strip() if data_version_path.exists() else cfg["dataset"]["version"],
        "base_model": cfg["model"]["name"],
        "lora": lora_cfg,
        "train_loss": train_result.training_loss,
        "eval_loss": eval_metrics.get("eval_loss"),
        "train_duration_minutes": round(duration_minutes, 2),
        "peak_vram_mb": round(peak_vram_mb, 1) if peak_vram_mb else None,
        "adapter_size_mb": round(adapter_size_mb, 2),
        "output_dir": str(output_dir),
        "git_commit": current_git_commit(),
    }
    result_path = experiments_dir / f"{experiment_id}.json"
    result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResult summary written to {result_path}")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
