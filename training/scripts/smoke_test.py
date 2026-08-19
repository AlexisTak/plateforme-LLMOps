"""Smoke test — run BEFORE any real training (mission rule 48).

Loads model + tokenizer, runs a forward pass, verifies LoRA gradients flow,
does a few optimizer steps, saves a checkpoint, reloads it, and runs one
inference. Uses a handful of in-memory examples — no real dataset needed.
Should finish in well under a minute on the RTX 4060.

Usage:
    python training/scripts/smoke_test.py
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import torch
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

MODEL_NAME = "unsloth/Llama-3.2-1B-Instruct"

DEMO_EXAMPLES = [
    {"user": "Je suis complètement débordé.", "assistant": '{"intent": "overwhelm", "next_action": {"title": "Choisis une seule tâche", "duration_minutes": 5, "difficulty": "low"}}'},
    {"user": "Je dois envoyer ma déclaration.", "assistant": '{"intent": "next_action", "next_action": {"title": "Ouvrir le site concerné", "duration_minutes": 2, "difficulty": "low"}}'},
    {"user": "J'ai très peu d'énergie aujourd'hui.", "assistant": '{"intent": "energy", "energy": "low", "next_action": {"title": "Répondre aux emails courts", "duration_minutes": 5, "difficulty": "low"}}'},
]


def build_batch(tokenizer, examples, max_length=512):
    texts = []
    for ex in examples:
        messages = [
            {"role": "user", "content": ex["user"]},
            {"role": "assistant", "content": ex["assistant"]},
        ]
        texts.append(tokenizer.apply_chat_template(messages, tokenize=False))
    enc = tokenizer(texts, return_tensors="pt", padding=True, truncation=True, max_length=max_length)
    enc["labels"] = enc["input_ids"].clone()
    return enc


def main() -> None:
    print(f"[1/8] loading tokenizer: {MODEL_NAME}")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    print(f"[2/8] loading base model in 4-bit: {MODEL_NAME}")
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        quantization_config=bnb_config,
        device_map={"": 0},
    )

    print("[3/8] attaching LoRA adapter")
    lora_config = LoraConfig(
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    print("[4/8] running forward + backward pass on demo batch")
    batch = build_batch(tokenizer, DEMO_EXAMPLES)
    batch = {k: v.to(model.device) for k, v in batch.items()}
    model.train()
    out = model(**batch)
    assert out.loss is not None, "no loss returned"
    out.loss.backward()

    grad_norms = [p.grad.norm().item() for p in model.parameters() if p.requires_grad and p.grad is not None]
    assert grad_norms, "no LoRA gradients found — adapter is not training"
    print(f"    loss={out.loss.item():.4f}, {len(grad_norms)} LoRA tensors have gradients, max grad norm={max(grad_norms):.4f}")

    print("[5/8] running a few optimizer steps")
    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=2e-4)
    for step in range(3):
        batch = build_batch(tokenizer, DEMO_EXAMPLES)
        batch = {k: v.to(model.device) for k, v in batch.items()}
        out = model(**batch)
        out.loss.backward()
        optimizer.step()
        optimizer.zero_grad()
        print(f"    step {step}: loss={out.loss.item():.4f}")

    tmp_dir = Path(tempfile.mkdtemp(prefix="biscuits_smoke_"))
    try:
        print(f"[6/8] saving adapter checkpoint to {tmp_dir}")
        model.save_pretrained(str(tmp_dir))

        print("[7/8] reloading adapter checkpoint")
        from peft import PeftModel

        base = AutoModelForCausalLM.from_pretrained(
            MODEL_NAME,
            quantization_config=bnb_config,
            device_map={"": 0},
        )
        reloaded = PeftModel.from_pretrained(base, str(tmp_dir))

        print("[8/8] running one inference with the reloaded adapter")
        reloaded.eval()
        prompt = tokenizer.apply_chat_template(
            [{"role": "user", "content": "Je dois trier mes mails en retard."}],
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = tokenizer(prompt, return_tensors="pt").to(reloaded.device)
        with torch.no_grad():
            generated = reloaded.generate(**inputs, max_new_tokens=80, do_sample=False)
        text = tokenizer.decode(generated[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
        print(f"    generated: {text!r}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    print("\nSMOKE TEST PASSED — safe to proceed to a real training run.")


if __name__ == "__main__":
    main()
