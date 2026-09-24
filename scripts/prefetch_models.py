"""Downloads into the HuggingFace cache what the RAG needs, so it keeps working in
offline mode (BISCUITS_OFFLINE=1, the .env.example default): the embedding model
(rag/settings.py) and the chunker's tokenizer (rag/chunker.py). Run by the setup
scripts; extra HF repo ids (e.g. a project's base model) can be passed as arguments.

    python scripts/prefetch_models.py [repo_id ...]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# This script's whole point is to download: ignore an offline setting inherited from the shell.
for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
    os.environ.pop(name, None)

from huggingface_hub import snapshot_download  # noqa: E402

from rag.chunker import MODEL_NAME as CHUNKER_TOKENIZER  # noqa: E402
from rag.settings import EMBEDDING_MODEL  # noqa: E402

# The chunker only loads the tokenizer: skip the weights of the (1B) model.
TOKENIZER_ONLY = ["*.json", "*.model", "*.txt", "*.tiktoken"]


def main(extra: list[str]) -> int:
    targets = [(EMBEDDING_MODEL, None), (CHUNKER_TOKENIZER, TOKENIZER_ONLY)] + [(repo, None) for repo in extra]
    failed = []
    for repo_id, patterns in targets:
        print(f"-> {repo_id}{' (tokenizer only)' if patterns else ''}", flush=True)
        try:
            snapshot_download(repo_id, allow_patterns=patterns)
        except Exception as exc:  # network, auth, unknown repo — report and keep going
            print(f"   failed: {exc}", file=sys.stderr)
            failed.append(repo_id)
    if failed:
        print(f"Not downloaded: {', '.join(failed)} - offline mode will fail on them.", file=sys.stderr)
        return 1
    print("Models cached - offline mode can use them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
