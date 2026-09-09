# Model Card — Biscuits Focus

**Version:** 0.1 (dataset-v0.3, experiment_003, quantized Q4_K_M)
**Base model:** [unsloth/Llama-3.2-1B-Instruct](https://huggingface.co/unsloth/Llama-3.2-1B-Instruct) (ungated mirror of `meta-llama/Llama-3.2-1B-Instruct`)
**Method:** QLoRA fine-tuning (r=32, alpha=64, dropout=0.05, target modules: q/k/v/o_proj + gate/up/down_proj) — see [training/configs/lora_r32.yaml](training/configs/lora_r32.yaml)
**Dataset:** [dataset-v0.3](docs/DATASET_GUIDELINES.md), 117 hand-authored examples across 6 categories (91 train / 9 validation / 17 test)
**Export:** merged → GGUF f16 → Ollama Q4_K_M — see [evaluation/performance.md](evaluation/performance.md)
**License:** inherits Llama 3.2's license (see [Meta's Llama 3.2 license](https://github.com/meta-llama/llama-models/blob/main/models/llama3_2/LICENSE)) — this project's own code is not separately licensed here; add a LICENSE file before any public release.

## What this model is

A small (1B parameter), locally-runnable assistant fine-tuned to help break down tasks, propose a single concrete next action, prioritize between competing tasks, and reduce cognitive load when a user reports feeling overwhelmed. It's aimed at people with attention/organization difficulties, but works as a general task-organization assistant.

## What this model is NOT

- **Not a medical device.** It does not diagnose, treat, or claim to manage ADHD or any other condition.
- **Not a source of medical advice.** It's trained to refuse diagnosis/treatment/medication questions and redirect to a professional — see `datasets/safety/` and [evaluation/report.md](evaluation/report.md) for how it performs on this.
- **Not a knowledge base.** Facts, methods, and product documentation come from RAG ([rag/](rag)), not from the fine-tuned weights — see [README.md](README.md) for the fine-tuning/RAG/memory separation.

## Intended use

- Local, offline task organization assistant (via Ollama or the training/inference stack in this repo).
- Structured JSON output for integration into task-management apps (schema: [docs/OUTPUT_SCHEMA.json](docs/OUTPUT_SCHEMA.json)).
- Optionally grounded with RAG documents (organizational methods, product docs, and — if the user adds them — research papers, treated as informational context only, never as instructions; see [rag/documents/README.md](rag/documents/README.md)).

## Prohibited use

- Diagnosing ADHD or any medical/psychological condition.
- Prescribing, recommending, or discussing medication dosage.
- Presenting model output as professional medical, psychiatric, or therapeutic advice.
- Any safety-critical decision-making without human review.

## Evaluation summary

See [evaluation/report.md](evaluation/report.md) (behavior benchmark, base vs LoRA r=8/16/32) and [evaluation/quantization_report.md](evaluation/quantization_report.md) (Q4/Q8/F16 comparison). Headline numbers, LoRA r=32 vs base model on a 14-prompt benchmark:

| | JSON valid | Concise | Safety pass |
|---|---|---|---|
| Base (no fine-tune) | 0% | 35.7% | 100%* |
| Biscuits Focus (r=32) | 100% | 85.7% | 100% |

\* Base model's safety pass rate largely reflects Llama's own RLHF alignment, not this project's fine-tuning — see limits below.

## Known limitations

- **Dataset is still small** (117 examples). Behavior generalizes to prompts resembling training examples better than to genuinely novel phrasing; expect rough edges on out-of-distribution requests.
- **Safety is not perfect.** During evaluation, the r=16 variant produced one non-refusal on a medication-related prompt ("arrêter mon traitement psychiatrique") — see [evaluation/report.md](evaluation/report.md). More `datasets/safety/` coverage on treatment-continuation questions specifically is a known gap.
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
