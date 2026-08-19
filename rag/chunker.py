"""Chunk markdown documents into token-budgeted pieces, splitting on paragraph
boundaries first so a chunk never cuts a sentence in half unless a single
paragraph alone exceeds the budget.

Token counts use the same tokenizer as training/inference (Llama 3.2 1B) so
chunk sizes are meaningful relative to the model's actual context handling.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from transformers import AutoTokenizer

MODEL_NAME = "unsloth/Llama-3.2-1B-Instruct"
ROOT = Path(__file__).resolve().parent.parent

_tokenizer = None


def get_tokenizer():
    global _tokenizer
    if _tokenizer is None:
        _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    return _tokenizer


@dataclass
class Chunk:
    doc_id: str
    category: str
    chunk_id: str
    text: str
    token_count: int


def _token_len(text: str) -> int:
    return len(get_tokenizer()(text)["input_ids"])


def chunk_text(text: str, doc_id: str, category: str, max_tokens: int, overlap_tokens: int) -> list[Chunk]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    chunks: list[Chunk] = []
    current_paras: list[str] = []
    current_tokens = 0

    def flush():
        nonlocal current_paras, current_tokens
        if not current_paras:
            return
        chunk_text_value = "\n\n".join(current_paras)
        chunk_id = f"{doc_id}::{len(chunks)}"
        chunks.append(Chunk(doc_id=doc_id, category=category, chunk_id=chunk_id, text=chunk_text_value, token_count=_token_len(chunk_text_value)))

    for para in paragraphs:
        para_tokens = _token_len(para)

        if para_tokens > max_tokens:
            flush()
            current_paras, current_tokens = [], 0
            chunk_id = f"{doc_id}::{len(chunks)}"
            chunks.append(Chunk(doc_id=doc_id, category=category, chunk_id=chunk_id, text=para, token_count=para_tokens))
            continue

        if current_tokens + para_tokens > max_tokens and current_paras:
            flush()
            if overlap_tokens > 0 and current_paras:
                overlap_para = current_paras[-1]
                current_paras = [overlap_para]
                current_tokens = _token_len(overlap_para)
            else:
                current_paras, current_tokens = [], 0

        current_paras.append(para)
        current_tokens += para_tokens

    flush()
    return chunks


def iter_documents(documents_dir: Path):
    """Yields (path, category) for every document — category is the immediate
    parent folder name under <project>/rag/documents/ (methods, research, ...)."""
    for path in sorted(documents_dir.glob("*/*.md")):
        yield path, path.parent.name


def chunk_all_documents(documents_dir: Path, max_tokens: int, overlap_tokens: int) -> list[Chunk]:
    all_chunks: list[Chunk] = []
    for path, category in iter_documents(documents_dir):
        text = path.read_text(encoding="utf-8")
        all_chunks.extend(chunk_text(text, doc_id=path.stem, category=category, max_tokens=max_tokens, overlap_tokens=overlap_tokens))
    return all_chunks


def write_chunks(chunks: list[Chunk], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, required=True, help="e.g. projects/biscuits-focus")
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--overlap-tokens", type=int, default=50)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    output = args.output or (args.project_dir / "rag" / "chunks" / "chunks.jsonl")

    chunks = chunk_all_documents(args.project_dir / "rag" / "documents", args.max_tokens, args.overlap_tokens)
    write_chunks(chunks, output)
    print(f"{len(chunks)} chunks written to {output} (max_tokens={args.max_tokens}, overlap={args.overlap_tokens})")
    for c in chunks:
        print(f"  {c.chunk_id}: {c.token_count} tokens")
