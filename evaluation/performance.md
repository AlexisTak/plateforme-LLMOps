# Performance Report — Biscuits Focus

Hardware: RTX 4060 8GB VRAM, Ryzen 5 5500, 16GB RAM (see [docs/ENVIRONMENT.md](../docs/ENVIRONMENT.md)). Numbers below are from [evaluation/quantization_report.py](quantization_report.py), 14-prompt benchmark, via the Ollama HTTP API.

| Variant | File size | Tokens/sec | Avg latency (14 prompts, ≤200 tok) | First load |
|---|---|---|---|---|
| **biscuits-focus (Q4_K_M)** | **807 MB** | **229.9** | **0.92s** | **4.36s** |
| biscuits-focus-q8 (Q8_0) | 1331 MB | 154.7 | 1.23s | 4.30s |
| biscuits-focus-f16 (F16) | 2560 MB | 45.6 | 2.78s | 6.78s |

**Recommendation: Q4_K_M.** Smallest file, fastest generation, and JSON-output quality at least as good as F16 on this benchmark (see [evaluation/quantization_report.md](quantization_report.md) — Q5_K_M isn't available through Ollama's built-in quantizer on this version, so the comparison is Q4/Q8/F16 rather than Q4/Q5/Q8 as originally planned).

## Training-time numbers (RTX 4060, QLoRA 4-bit)

From [experiments/](../experiments/) (dataset-v0.3, 91 train examples):

| Experiment | LoRA r | Peak VRAM | Train time | Adapter size |
|---|---|---|---|---|
| experiment_002 | 8 | 2.36 GB | ~1.25 min | 10.8 MB |
| experiment_001 | 16 | 2.46 GB | ~1.30 min | 21.5 MB |
| experiment_003 | 32 | 2.55 GB | ~1.24 min | 43.0 MB |

Training on this 1B model is cheap: under 8GB VRAM headroom used even at r=32, full run in ~1.3 minutes on a tiny dataset (scales roughly linearly with dataset size and epoch count).

## What this doesn't cover yet

- CPU-only inference speed (Ollama numbers above ran on GPU) — worth a separate pass once the model is meant to run on machines without a GPU (mission rule 39/22's "compatible CPU autant que possible").
- Multi-turn / long-context latency (benchmark prompts are single-turn, ≤200 output tokens).
