"""Normalize uploaded files (PDF, TXT, MD) into plain text stored as .md in
rag/documents/ — the rest of the pipeline (chunker, index, retriever) only
ever deals with .md files, so this is the one place format differences live.
"""

from __future__ import annotations

import io
import re

from pypdf import PdfReader

MAX_UPLOAD_BYTES = 150 * 1024 * 1024  # 150 MB — a few hundred pages of text-bearing PDF, catches accidental huge binaries
SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md"}


class IngestError(ValueError):
    pass


def sanitize_basename(filename: str) -> str:
    """Derive a safe .md basename from an arbitrary uploaded filename."""
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    stem = re.sub(r"[^a-zA-Z0-9_\-]+", "_", stem).strip("_")
    if not stem:
        raise IngestError("filename has no usable characters after sanitization")
    return f"{stem}.md"


def extract_text(filename: str, raw: bytes) -> str:
    if len(raw) > MAX_UPLOAD_BYTES:
        raise IngestError(f"file too large ({len(raw) / 1024 / 1024:.1f} MB > {MAX_UPLOAD_BYTES / 1024 / 1024:.0f} MB limit)")

    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in SUPPORTED_EXTENSIONS:
        raise IngestError(f"unsupported file type '{ext}' — supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")

    if ext == ".pdf":
        text = _extract_pdf_text(raw)
    else:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise IngestError("file must be UTF-8 text")

    text = text.strip()
    if not text:
        raise IngestError("no extractable text found in file")
    return text


def _extract_pdf_text(raw: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(raw))
    except Exception as e:
        raise IngestError(f"could not read PDF: {e}")

    if reader.is_encrypted:
        raise IngestError("PDF is password-protected — decrypt it before uploading")

    pages_text = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        page_text = page_text.strip()
        if page_text:
            pages_text.append(page_text)

    if not pages_text:
        raise IngestError("no extractable text found — this PDF may be scanned images without OCR text")

    return "\n\n".join(pages_text)
