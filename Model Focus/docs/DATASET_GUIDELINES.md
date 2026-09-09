# Dataset Guidelines — Biscuits Focus

## Principle

Quality > diversity > quantity. This model learns *behavior* (decomposition, prioritization, concision, non-judgment), not facts. A few hundred sharp examples beat tens of thousands of generic ones.

## Format

Hugging Face `datasets`-compatible JSONL, one conversation per line:

```json
{"messages": [
  {"role": "system", "content": "..."},
  {"role": "user", "content": "..."},
  {"role": "assistant", "content": "..."}
]}
```

- `system` message is optional per-example (defaults to [training/configs/system_prompt.txt](../training/configs/system_prompt.txt) if omitted at load time) — kept minimal, business logic lives in the fine-tune, not the prompt (mission rule 18).
- `assistant` content is either natural free text (conversational category) or a single JSON object as a string (structured categories) matching [docs/OUTPUT_SCHEMA.json](OUTPUT_SCHEMA.json). Never mix prose and JSON in one assistant turn.
- Structured responses with a `next_action` or a `tasks` list should include a `tip` (per next_action) / `tips` (parallel array to `tasks`) — one concrete, specific trick per step, not generic encouragement ("tu peux le faire"). This is what makes a breakdown actually useful instead of just a checklist.

## Categories (directories under `datasets/`)

| Directory | Behavior taught |
|---|---|
| `instructions` | general instruction-following in the assistant's voice/style |
| `conversations` | natural free-text replies where structured JSON would be wrong (reassurance, clarification, chit-chat) |
| `tasks` | task_breakdown, next_action, capture mentale (unstructured brain-dump -> structured list) |
| `overwhelm` | reducing complexity, picking ONE action, non-judgmental tone, short replies |
| `planning` | prioritization (urgency + importance + duration + energy + deadline + context, never a single-axis sort), interruption/resume handling |
| `safety` | refusing *personalized* diagnosis/dosage/prescription questions ("do I have ADHD", "should I take/stop X", "what dose") while still offering organizational help where appropriate. **General factual questions about ADHD or its treatments** ("how does methylphenidate work", "is ADHD curable") are answered factually instead — see `conversations` for those examples — never refused just for touching the topic of medication/diagnosis in the abstract. |

## French requirement

Every category must include: informal/SMS French with typos (`"jsuis"`, `"jai"`, no accents), short fragments, formal French, and common FR/EN tech code-switching. See mission rule 41. Do not sanitize user-turn French — the model must parse it as-is; only assistant turns are held to a clean-writing bar.

## Synthetic generation pipeline

Never bulk-generate blindly with a single LLM pass.

```
Generation -> Validation -> Deduplication -> Quality filtering -> Human review -> Final dataset
```

- Generation: draft candidates per category (can use an LLM), tagged with category + generation batch id.
- Validation: run `scripts/validate_dataset.py` (schema, roles, JSON validity, length, safety keyword scan).
- Deduplication: run `scripts/deduplicate_dataset.py` (exact + near-duplicate via embedding cosine similarity).
- Quality filtering: drop examples that are too short/long, incoherent, or duplicate an existing intent+structure combo.
- Human review: every batch gets a manual pass before merging into `data/raw/`.
- Final dataset: only reviewed examples move to `data/raw/`, then through cleaning into `data/train|validation|test/`.

## Split

80/10/10 train/validation/test, stratified by category. Test set is frozen once created — do not resample it when adding more training data later; add new examples to train/validation only, or bump the dataset version and re-split from scratch (see versioning below).

Before finalizing a split, run the semantic near-duplicate check (`scripts/deduplicate_dataset.py --check-splits`) across train/test to catch paraphrase leakage, not just exact-string leakage.

## Versioning

Dataset directories/snapshots are tagged `dataset-vX.Y` (e.g. `dataset-v0.1`). Every training run config records which dataset version it used (see `training/configs/*.yaml` -> `dataset.version`). Never silently mutate a version already used by a completed training run — cut a new version instead.

## What NOT to put in the fine-tuning dataset

- Large factual knowledge dumps (organizational methods, product docs) — that's RAG's job, see [rag/](../rag).
- User-specific data (names, real project details) — that's user memory, never trained into weights.
- A **personalized** diagnosis, dosage, or prescription recommendation as a *correct* assistant answer — that's always `safety`-category refusal territory, no exception. General, non-personalized factual education about ADHD or how a treatment works in general is fine in `conversations` (revised — see the `safety` row above); the line is "about this specific person" vs "about the topic in general".
