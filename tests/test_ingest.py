"""_extract_docx_text parses an uploaded, untrusted .docx's word/document.xml with
stdlib ElementTree, which resolves DTD-declared internal entities — a "billion
laughs" exponential-expansion DoS vector (and XXE, for external entities) if a
DOCTYPE is allowed through. Real Word documents never declare one."""

from __future__ import annotations

import io
import zipfile

import pytest

from rag.ingest import IngestError, extract_text

NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _docx(xml_bytes: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("word/document.xml", xml_bytes)
    return buf.getvalue()


def test_docx_with_doctype_entity_is_rejected():
    malicious = f"""<?xml version="1.0"?>
<!DOCTYPE root [<!ENTITY a "pwned">]>
<w:document xmlns:w="{NS}"><w:body><w:p><w:t>&a;</w:t></w:p></w:body></w:document>""".encode()
    with pytest.raises(IngestError):
        extract_text("malicious.docx", _docx(malicious))


def test_docx_without_doctype_still_extracts_text():
    legit = f"""<?xml version="1.0"?>
<w:document xmlns:w="{NS}"><w:body><w:p><w:t>hello world</w:t></w:p></w:body></w:document>""".encode()
    assert extract_text("legit.docx", _docx(legit)) == "hello world"
