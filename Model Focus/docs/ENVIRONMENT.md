# Environment Audit — Biscuits Focus

> Ce document conserve l'audit matériel Windows d'origine. Le projet dispose
> désormais aussi de scripts Linux (`setup-linux.sh`, `start.sh`, `stop.sh`) ;
> les valeurs système ci-dessous ne décrivent donc pas toutes les machines prises
> en charge.

Date: 2026-08-17

## System

| Item | Value |
|---|---|
| OS | Windows 11 Professionnel 64-bit (build 10.0.26200) |
| CPU | AMD Ryzen 5 5500 — 6 cores / 12 threads |
| RAM | 15.87 GB total |
| Disk (C:) | 153.76 GB free / 776.7 GB used |
| Git | 2.54.0.windows.1 |

## GPU / CUDA

| Item | Value |
|---|---|
| GPU | NVIDIA GeForce RTX 4060 |
| VRAM | 8188 MiB (~8 GB) |
| Driver | 610.62 |
| Compute capability | 8.9 (Ada Lovelace) |
| System CUDA toolkit (nvcc) | not installed — not required, PyTorch CUDA wheels ship their own runtime |

Compute cap 8.9 supports bf16, 4-bit (bitsandbytes NF4), Flash-Attention 2. Driver is new enough for CUDA 12.4+ wheels.

## Python

Multiple Python installs found on system (messy global state):
- `pythoncore-3.14-64` (used by default `pip`/`py`)
- `pythoncore-3.11-64` ← **chosen for this project**
- Hermes-agent venv (3.11.15, unrelated tool, not for this project)

**Decision:** dedicated venv at `./.venv` built from `pythoncore-3.11-64`. Python 3.14 is too new — PyTorch, bitsandbytes and flash-attn wheels do not reliably target it yet. 3.11 has the widest wheel coverage across the whole stack (torch, peft, trl, bitsandbytes, llama-cpp-python).

Activate: `.venv\Scripts\Activate.ps1` (PowerShell) or `.venv/Scripts/python.exe` directly.

## Ollama

- Version: 0.32.14
- Already pulled before audit: `llama3.2:3b`, `qwen3.5:0.8b`, `qwen3.5:4b`, `hermes3:3b`, `kimi-k3:cloud`
- `llama3.2:1b` — **not present, pulled during audit** (`ollama pull llama3.2:1b`, 1.3 GB)

## Constraints this drives

- **8 GB VRAM** → QLoRA (4-bit NF4) is the safe default for training; plain LoRA in bf16 on a 1B model should also fit (1B params ≈ 2 GB in bf16 + optimizer states), but QLoRA leaves headroom for larger batch/seq length. Both will be benchmarked (see [training/README.md](../training) once created).
- **16 GB system RAM** → keep dataset loading streaming/lazy where possible, avoid loading huge tokenized caches fully in RAM, avoid large `num_proc` in `datasets.map` (spawns processes, each duplicating memory).
- **CPU inference target** → GGUF quantization (Q4/Q5/Q8 compared later) is mandatory for the "runs on CPU" requirement, on top of the GPU-trained LoRA.
- **No system CUDA toolkit** → do not use anything that requires compiling CUDA kernels from source unless a prebuilt wheel exists (e.g. bitsandbytes ships prebuilt Windows CUDA wheels since 0.43+; flash-attn does NOT have reliable prebuilt Windows wheels — skip it, not required for a 1B model).

## Next step

Install minimal ML stack into `.venv`, verify each library imports and detects the GPU, then run the smoke test (rule #48 in the mission spec) before any real training.
