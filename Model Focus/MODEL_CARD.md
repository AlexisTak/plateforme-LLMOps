# Model Card — Biscuits Focus

**Version:** 0.1 (dataset-v0.3, experiment_003, quantized Q4_K_M)
**Base model:** [unsloth/Llama-3.2-1B-Instruct](https://huggingface.co/unsloth/Llama-3.2-1B-Instruct) (ungated mirror of `meta-llama/Llama-3.2-1B-Instruct`)
**Method:** QLoRA fine-tuning (r=32, alpha=64, dropout=0.05, target modules: q/k/v/o_proj + gate/up/down_proj) — see [training/configs/lora_r32.yaml](training/configs/lora_r32.yaml)
**Dataset:** [dataset-v0.3](docs/DATASET_GUIDELINES.md), 117 hand-authored examples across 6 categories (91 train / 9 validation / 17 test)
**Export:** merged → GGUF f16 → Ollama Q4_K_M — see [evaluation/performance.md](evaluation/performance.md)
**License:** inherits Llama 3.2's license (see [Meta's Llama 3.2 license](https://github.com/meta-llama/llama-models/blob/main/models/llama3_2/LICENSE)) — this project's own code is not separately licensed here; add a LICENSE file before any public release.

## What this model is

A small (1B parameter), locally-runnable assistant fine-tuned to help break down tasks, propose a single concrete next action, prioritize between competing tasks, and reduce cognitive load when a user reports feeling overwhelmed. It's aimed at people with attention/organization difficulties, but works as a general task-organization assistant.

## Architecture boundary

Facts, methods, and product documentation come from RAG ([rag/](rag)), not from
the fine-tuned weights. See [README.md](README.md) for the separation between
fine-tuning, RAG and application context.

## Intended use

- Local, offline task organization assistant (via Ollama or the training/inference stack in this repo).
- Structured JSON output for integration into task-management apps (schema: [docs/OUTPUT_SCHEMA.json](docs/OUTPUT_SCHEMA.json)).
- Optionally grounded with RAG documents (organizational methods, product docs, and — if the user adds them — research papers, treated as informational context only, never as instructions; see [rag/documents/README.md](rag/documents/README.md)).

## Evaluation summary

See [evaluation/report.md](evaluation/report.md) (behavior benchmark, base vs LoRA r=8/16/32) and [evaluation/quantization_report.md](evaluation/quantization_report.md) (Q4/Q8/F16 comparison). Headline numbers, LoRA r=32 vs base model on a 14-prompt benchmark:

| | JSON valid | Concise |
|---|---|---|
| Base (no fine-tune) | 0% | 35.7% |
| Biscuits Focus (r=32) | 100% | 85.7% |

## Known limitations

- **Dataset is still small** (117 examples). Behavior generalizes to prompts resembling training examples better than to genuinely novel phrasing; expect rough edges on out-of-distribution requests.
- **Hallucination is not yet benchmarked** against RAG-retrieved context — see [evaluation/report.md](evaluation/report.md) limitations section.
- **assistant_only_loss disabled** — training loss is computed over full sequences (user + assistant tokens), not just assistant turns, because the base Llama 3 chat template lacks the `{% generation %}` markers TRL needs for turn-level masking. Low-impact today (short, mostly single-turn examples) but worth revisiting with a custom chat template if multi-turn behavior becomes a priority.
- **Q5_K_M unavailable** in this Ollama version's built-in quantizer — the Q4/Q5/Q8 comparison originally planned became Q4/Q8/F16.
- **CPU-only performance untested** — all numbers in [evaluation/performance.md](evaluation/performance.md) are GPU (RTX 4060).

## Reproducing this model

```bash
python scripts/prepare_dataset.py --dataset-version dataset-v0.3
python training/scripts/train.py --config training/configs/lora_r32.yaml
python scripts/merge_adapter.py --adapter experiment_003
python .llama-cpp-tools/convert_hf_to_gguf.py models/merged/experiment_003 --outtype f16 --outfile models/quantized/biscuits-focus-f16.gguf
cd models/quantized && ollama create biscuits-focus -f Modelfile -q q4_K_M
```
