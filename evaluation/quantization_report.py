"""Compare quantization levels of the Ollama-exported model (mission rule 35):
size, tokens/sec, first-token latency, RAM/model-file-size, JSON validity on
the same benchmark as evaluation/run.py.

Talks to the local Ollama HTTP API (localhost:11434) rather than shelling out
to `ollama run`, so output isn't polluted by TTY control codes.

Usage:
    python evaluation/quantization_report.py
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
BENCHMARK_PATH = Path(__file__).parent / "benchmark.jsonl"
REPORT_PATH = Path(__file__).parent / "quantization_report.md"
OLLAMA_URL = "http://localhost:11434/api/generate"

VARIANTS = ["biscuits-focus-q4", "biscuits-focus-q8", "biscuits-focus-f16"]


def load_benchmark() -> list[dict]:
    with BENCHMARK_PATH.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def get_model_size_bytes(model: str) -> int | None:
    result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
    for line in result.stdout.splitlines():
        if line.startswith(model):
            parts = line.split()
            # e.g. "biscuits-focus-q4:latest  10324a9be9f7  807 MB  2 minutes ago"
            for i, tok in enumerate(parts):
                if tok in ("MB", "GB"):
                    value = float(parts[i - 1])
                    return int(value * (1024**3 if tok == "GB" else 1024**2))
    return None


def generate(model: str, prompt: str) -> dict:
    start = time.time()
    resp = requests.post(
        OLLAMA_URL,
        json={"model": model, "prompt": prompt, "stream": False, "options": {"num_predict": 200}},
        timeout=240,
    )
    resp.raise_for_status()
    elapsed = time.time() - start
    data = resp.json()
    return {
        "response": data.get("response", ""),
        "wall_seconds": elapsed,
        "eval_count": data.get("eval_count"),  # tokens generated
        "eval_duration_ns": data.get("eval_duration"),  # generation-only time
        "load_duration_ns": data.get("load_duration"),
    }


def main() -> None:
    benchmark = load_benchmark()
    print(f"Loaded {len(benchmark)} benchmark prompts")

    results = {}
    for model in VARIANTS:
        print(f"\n=== {model} ===")
        size_bytes = get_model_size_bytes(model)
        rows = []
        for item in benchmark:
            gen = generate(model, item["user"])
            json_valid = False
            stripped = gen["response"].strip()
            if stripped.startswith("{"):
                try:
                    json.loads(stripped)
                    json_valid = True
                except json.JSONDecodeError:
                    pass
            tokens_per_sec = None
            if gen["eval_count"] and gen["eval_duration_ns"]:
                tokens_per_sec = gen["eval_count"] / (gen["eval_duration_ns"] / 1e9)
            rows.append({**gen, "json_valid": json_valid, "tokens_per_sec": tokens_per_sec, "id": item["id"]})
            print(f"  [{item['id']}] {gen['wall_seconds']:.2f}s, {tokens_per_sec:.1f} tok/s" if tokens_per_sec else f"  [{item['id']}] {gen['wall_seconds']:.2f}s")

        valid_rates = [r["json_valid"] for r in rows]
        tok_speeds = [r["tokens_per_sec"] for r in rows if r["tokens_per_sec"]]
        results[model] = {
            "size_bytes": size_bytes,
            "n": len(rows),
            "json_valid_pct": round(100 * sum(valid_rates) / len(valid_rates), 1),
            "avg_tokens_per_sec": round(sum(tok_speeds) / len(tok_speeds), 1) if tok_speeds else None,
            "avg_wall_seconds": round(sum(r["wall_seconds"] for r in rows) / len(rows), 2),
            "first_load_seconds": round((rows[0]["load_duration_ns"] or 0) / 1e9, 2),
        }

    lines = ["# Quantization Report — Biscuits Focus\n"]
    lines.append("Base: experiment_003 (LoRA r=32) merged, converted to GGUF, quantized via Ollama's built-in quantizer.\n")
    lines.append("Note: Q5_K_M is not supported by Ollama's quantizer on this version (supported: F32, F16, Q4_K_S, Q4_K_M, Q8_0) — comparing Q4_K_M / Q8_0 / F16 instead.\n")
    lines.append("| Variant | Size | JSON valid % | Avg tok/s | Avg latency | First load |")
    lines.append("|---|---|---|---|---|---|")
    for model, r in results.items():
        size_mb = round(r["size_bytes"] / 1024 / 1024, 0) if r["size_bytes"] else "—"
        lines.append(
            f"| {model} | {size_mb} MB | {r['json_valid_pct']} | {r['avg_tokens_per_sec']} | {r['avg_wall_seconds']}s | {r['first_load_seconds']}s |"
        )

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport written to {REPORT_PATH}")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
