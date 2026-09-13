"""Benchmark base model vs each trained LoRA adapter on evaluation/benchmark.jsonl.

Checks (heuristic, no LLM judge — small model, offline):
  - output format: natural text or JSON, according to the project setting
  - concision: response length under a per-prompt budget
  - action quality and RAG grounding: not measured by these format heuristics;
    see docs/RUNTIME_FIXES.md for human review criteria.

Usage:
    python evaluation/run.py --project-dir projects/biscuits-focus
"""

from __future__ import annotations

import gc
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

import sys

sys.path.insert(0, str(ROOT))
from inference.router import output_suffix
from evaluation.reports import capture_metadata, save_report


def discover_variants(project_dir: Path) -> list[tuple[str, Path | None, str]]:
    """(label, adapter_path, base_model) for every adapter actually on disk in
    this project, plus one "base (no LoRA)" entry for the project's own base
    model — discovered instead of hardcoded, so a new config never silently
    drops out of evaluation (see AUDIT.md 2.2). Each adapter's base model comes
    from its own adapter_config.json, never assumed."""
    adapters_dir = project_dir / "models" / "adapters"
    meta = json.loads((project_dir / "meta.json").read_text(encoding="utf-8"))
    default_base_model = meta.get("inference_model") or meta["base_model"]

    variants: list[tuple[str, Path | None, str]] = [(f"base ({default_base_model}, no LoRA)", None, default_base_model)]

    for adapter_dir in sorted(adapters_dir.iterdir()) if adapters_dir.exists() else []:
        config_path = adapter_dir / "adapter_config.json"
        if not adapter_dir.is_dir() or not config_path.exists():
            continue
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
        variants.append((adapter_dir.name, adapter_dir, cfg["base_model_name_or_path"]))

    return variants



def load_benchmark(benchmark_path: Path) -> list[dict]:
    items = []
    seen_ids: set[str] = set()
    with benchmark_path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if line:
                item = json.loads(line)
                missing = {"id", "category", "user", "checks"} - item.keys()
                if missing:
                    raise ValueError(f"{benchmark_path}:{line_number}: champs manquants: {sorted(missing)}")
                if item["id"] in seen_ids:
                    raise ValueError(f"{benchmark_path}:{line_number}: id dupliqué: {item['id']}")
                if "review" not in item:
                    item["review"] = ["Réponse correcte, utile et adaptée à la demande"]
                if not isinstance(item["review"], list) or not item["review"]:
                    raise ValueError(f"{benchmark_path}:{line_number}: 'review' doit contenir au moins un critère")
                seen_ids.add(item["id"])
                items.append(item)
    return items


def load_model(base_model: str, adapter_path: Path | None):
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    model = AutoModelForCausalLM.from_pretrained(base_model, quantization_config=bnb_config, device_map={"": 0})
    if adapter_path is not None:
        model = PeftModel.from_pretrained(model, str(adapter_path))
    model.eval()
    return model


def generate(model, tokenizer, system_prompt: str, user_text: str, max_new_tokens: int = 200) -> str:
    import torch
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ]
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(prompt, return_tensors="pt", add_special_tokens=False).to(model.device)
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False, pad_token_id=tokenizer.pad_token_id)
    return tokenizer.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip()


def score(item: dict, response: str, output_mode: str = "natural") -> dict:
    checks = item["checks"]
    result = {
        "id": item["id"],
        "category": item["category"],
        "prompt": item.get("user", ""),
        "review": item.get("review", ["Réponse correcte, utile et adaptée à la demande"]),
        "response": response,
    }

    parsed = None
    stripped = response.strip()
    if stripped.startswith("{"):
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            parsed = None

    if output_mode == "json":
        result["json_valid"] = parsed is not None
        expected_keys = checks.get("expect_keys", [])
        result["has_expected_keys"] = parsed is not None and all(key in parsed for key in expected_keys)
        result["plain_text"] = None
    elif output_mode == "flexible":
        result["json_valid"] = None
        result["has_expected_keys"] = None
        result["plain_text"] = None
    else:
        # Natural mode preserves the contract of existing projects, including
        # benchmarks that still contain old expect_json flags.
        result["json_valid"] = None
        result["has_expected_keys"] = None
        try:
            json.loads(stripped)
            is_json = True
        except (ValueError, TypeError):
            is_json = False
        result["plain_text"] = bool(stripped) and not is_json and not stripped.startswith(("{", "[", "```"))

    result["concise"] = bool(stripped) and len(response) <= checks["max_chars"]

    return result


def aggregate(rows: list[dict]) -> dict:
    def stats(key):
        vals = [r[key] for r in rows if r.get(key) is not None]
        passed = sum(bool(value) for value in vals)
        return passed, len(vals), round(100 * passed / len(vals), 1) if vals else None

    plain_passed, plain_total, plain_pct = stats("plain_text")
    json_passed, json_total, json_pct = stats("json_valid")
    keys_passed, keys_total, keys_pct = stats("has_expected_keys")
    concise_passed, concise_total, concise_pct = stats("concise")

    return {
        "n": len(rows),
        "plain_text_passed": plain_passed,
        "plain_text_total": plain_total,
        "plain_text_pct": plain_pct,
        "json_valid_passed": json_passed,
        "json_valid_total": json_total,
        "json_valid_pct": json_pct,
        "has_expected_keys_passed": keys_passed,
        "has_expected_keys_total": keys_total,
        "has_expected_keys_pct": keys_pct,
        "concise_passed": concise_passed,
        "concise_total": concise_total,
        "concise_pct": concise_pct,
    }


def main() -> None:
    import argparse
    import torch
    from transformers import AutoTokenizer

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, required=True, help="e.g. projects/biscuits-focus")
    args = parser.parse_args()
    project_dir: Path = args.project_dir
    metadata = capture_metadata(project_dir)
    project_meta = json.loads((project_dir / "meta.json").read_text(encoding="utf-8"))
    output_mode = project_meta.get("output_mode", "natural")

    prompt_path = project_dir / "training" / "configs" / "system_prompt.txt"
    system_prompt = prompt_path.read_text(encoding="utf-8").strip() if prompt_path.exists() else "Tu es un assistant utile."

    benchmark_path = project_dir / "evaluation" / "benchmark.jsonl"
    benchmark = load_benchmark(benchmark_path)
    print(f"Loaded {len(benchmark)} benchmark prompts")

    variants = discover_variants(project_dir)
    print(f"Evaluating {len(variants)} variant(s): {[v[0] for v in variants]}")

    tokenizers: dict[str, AutoTokenizer] = {}

    all_results = {}
    for label, adapter_path, base_model in variants:
        print(f"\n=== {label} ===")
        if base_model not in tokenizers:
            tok = AutoTokenizer.from_pretrained(base_model)
            if tok.pad_token is None:
                tok.pad_token = tok.eos_token
            tokenizers[base_model] = tok
        tokenizer = tokenizers[base_model]
        model = load_model(base_model, adapter_path)
        rows = []
        for item in benchmark:
            # Match the output contract used by the runtime for this project.
            item_prompt = system_prompt + output_suffix(output_mode)
            response = generate(model, tokenizer, item_prompt, item["user"])
            rows.append(score(item, response, output_mode=output_mode))
            print(f"  [{item['id']}] {response[:80]!r}")
        all_results[label] = rows
        del model
        gc.collect()
        torch.cuda.empty_cache()

    lines = [f"# Evaluation Report — {project_meta.get('label', project_dir.name)}\n"]
    categories = ", ".join(sorted({item.get("category", "other") for item in benchmark}))
    lines.append(f"Benchmark: {len(benchmark)} prompts across {categories or 'no category'}.\n")
    lines.append(f"Generated: {metadata['generated_at']} | Dataset: {metadata['dataset_version']} | Scoring: {metadata['scoring_version']}\n")
    lines.append("Automated checks measure text format and concision only. Each raw output includes an explicit human-review rubric for action clarity, feasibility and honesty. RAG grounding is not evaluated by this benchmark.\n")

    lines.append("## Summary\n")
    lines.append("| Variant | n | Format texte | Concision |")
    lines.append("|---|---|---|---|")
    for label, rows in all_results.items():
        agg = aggregate(rows)
        lines.append(f"| {label} | {agg['n']} | {agg['plain_text_passed']}/{agg['plain_text_total']} | {agg['concise_passed']}/{agg['concise_total']} |")

    lines.append("\n## Raw outputs\n")
    for label, rows in all_results.items():
        lines.append(f"### {label}\n")
        for r in rows:
            flags = []
            flags.append(f"plain_text={r['plain_text']}")
            if r["json_valid"] is not None:
                flags.append(f"json_valid={r['json_valid']}")
            if r["has_expected_keys"] is not None:
                flags.append(f"expected_keys={r['has_expected_keys']}")
            flags.append(f"concise={r['concise']}")
            lines.append(f"- **{r['id']}** ({r['category']}) [{', '.join(flags)}]")
            lines.append(f"  - prompt: {r['prompt']}")
            lines.append(f"  - response: `{r['response'][:300]}`")
            lines.append(f"  - human review: {'; '.join(r['review'])}")
        lines.append("")

    report_path = project_dir / "evaluation" / "report.md"
    summary_json = {label: aggregate(rows) for label, rows in all_results.items()}
    save_report(project_dir, metadata, summary_json, all_results, "\n".join(lines))

    print(f"\nReport written to {report_path}")


if __name__ == "__main__":
    main()
