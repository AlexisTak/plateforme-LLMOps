"""Keeps at most one base+adapter model loaded in GPU memory at a time.

Chat requests are interactive — reloading a fresh 4-bit model on every message
(~5-10s) would make the UI feel broken. This singleton swaps lazily: same
(base model, adapter) pair as last time -> reuse; anything different -> unload
and reload.

Adapters live under a project's own models/adapters/ (projects are fully
isolated workspaces, see api/routes/projects.py). An adapter's actual base
model is read from its own adapter_config.json ("base_model_name_or_path",
written by PEFT at save time), never assumed from the project's meta.json —
that file is the only thing that can't drift out of sync with what the
adapter was really trained on.
"""

from __future__ import annotations

import gc
import json
import threading
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig


def _default_base_model(project_dir: Path) -> str:
    """Base model used for chat/eval when no adapter is selected — the
    project's own meta.json base_model."""
    meta = json.loads((project_dir / "meta.json").read_text(encoding="utf-8"))
    return meta["base_model"]


def resolve_base_model(project_dir: Path, adapter: str | None) -> str:
    if adapter is None:
        return _default_base_model(project_dir)
    adapter_config_path = project_dir / "models" / "adapters" / adapter / "adapter_config.json"
    if not adapter_config_path.exists():
        raise FileNotFoundError(f"adapter not found: {adapter_config_path}")
    cfg = json.loads(adapter_config_path.read_text(encoding="utf-8"))
    return cfg["base_model_name_or_path"]


def _adapter_fingerprint(project_dir: Path, adapter: str | None) -> float:
    """mtime of the adapter's weights file, or 0.0 with no adapter selected.

    Re-running a training sweep overwrites an existing experiment's adapter
    directory in place (see scripts/run_sweep.py --resume) — same name, new
    weights. Without this, the cache key below never changes and this process
    keeps serving the adapter it loaded first, silently, for its whole
    lifetime (hit once: retrained experiment_002 on a new dataset version,
    kept getting the old adapter's replies until the backend was restarted).
    """
    if adapter is None:
        return 0.0
    weights_path = project_dir / "models" / "adapters" / adapter / "adapter_model.safetensors"
    return weights_path.stat().st_mtime if weights_path.exists() else 0.0


class ModelManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tokenizer = None
        self._model = None
        self._current_base_model: str | None = None
        self._current_key: tuple[str, str | None, float] | None = None  # (project_dir, adapter, adapter_fingerprint)

    def available_adapters(self, project_dir: Path) -> list[str]:
        adapters_dir = project_dir / "models" / "adapters"
        if not adapters_dir.exists():
            return []
        return sorted(p.name for p in adapters_dir.iterdir() if p.is_dir() and (p / "adapter_config.json").exists())

    def _load_base(self, base_model: str):
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )
        return AutoModelForCausalLM.from_pretrained(base_model, quantization_config=bnb_config, device_map={"": 0})

    def _load_locked(self, project_dir: Path, adapter: str | None) -> None:
        """Assumes the caller already holds self._lock."""
        key = (str(project_dir), adapter, _adapter_fingerprint(project_dir, adapter))
        base_model = resolve_base_model(project_dir, adapter)

        if self._current_key == key and self._current_base_model == base_model and self._model is not None:
            return

        if self._model is not None:
            del self._model
            self._model = None
            gc.collect()
            torch.cuda.empty_cache()

        # tokenizer isn't cached across base models — a stale tokenizer from a
        # different base model would silently mis-tokenize every prompt.
        if self._tokenizer is None or self._current_base_model != base_model:
            self._tokenizer = AutoTokenizer.from_pretrained(base_model)
            if self._tokenizer.pad_token is None:
                self._tokenizer.pad_token = self._tokenizer.eos_token

        model = self._load_base(base_model)
        if adapter is not None:
            model = PeftModel.from_pretrained(model, str(project_dir / "models" / "adapters" / adapter))
        model.eval()

        self._model = model
        self._current_key = key
        self._current_base_model = base_model

    def ensure_loaded(self, project_dir: Path, adapter: str | None) -> None:
        with self._lock:
            self._load_locked(project_dir, adapter)

    def generate(
        self, project_dir: Path, message: str, adapter: str | None, system_prompt: str | None, max_new_tokens: int = 400,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        # Held for the whole call, not just the swap — otherwise a concurrent
        # request for a different project/adapter could unload the model
        # mid-generation.
        with self._lock:
            self._load_locked(project_dir, adapter)
            from inference.conversation import build_messages

            messages = build_messages(system_prompt or "Tu es un assistant utile.", message, history)
            # Leave room for the reply and cap interactive context to bound GPU use.
            context_limit = min(getattr(self._model.config, "max_position_embeddings", 4096), 4096)
            while len(messages) > 2:
                tokens = self._tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True)
                if len(tokens) + max_new_tokens <= context_limit:
                    break
                del messages[1:3]  # discard the oldest complete exchange
            prompt = self._tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            inputs = self._tokenizer(prompt, return_tensors="pt", add_special_tokens=False).to(self._model.device)
            if inputs["input_ids"].shape[1] + max_new_tokens > context_limit:
                raise ValueError("Message trop long pour la fenêtre de contexte du modèle")
            with torch.no_grad():
                out = self._model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    do_sample=False,
                    pad_token_id=self._tokenizer.pad_token_id,
                )
            return self._tokenizer.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip()


manager = ModelManager()
