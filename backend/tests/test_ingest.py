"""arXiv + PDF + sectionize tests.

arxiv tests are gated on network availability — we don't want CI to fail
because arxiv.org is flaky. Regex sectionization runs locally, always.
"""
from __future__ import annotations

import os

import pytest

from app.ingest import pdf_ingest
from app.ingest.arxiv_ingest import IngestError, normalize_arxiv_id
from app.ingest.sectionize import regex_sections


def test_arxiv_id_normalize():
    cases = [
        ("2604.01188", "2604.01188"),
        ("arxiv.org/abs/2604.01188", "2604.01188"),
        ("https://arxiv.org/abs/2604.01188v2", "2604.01188"),
        ("  2604.01188v1  ", "2604.01188"),
    ]
    for inp, want in cases:
        assert normalize_arxiv_id(inp) == want, f"got {normalize_arxiv_id(inp)} from {inp!r}"


def test_regex_sections_finds_standard_headings():
    text = """
1 Introduction
We introduce a new method for...

1.1 Background
Prior work...

2 Method
Our model...

2.1 Architecture
We use a six-layer...

3 Experiments
We evaluate on...
""".strip()
    sections = regex_sections(text)
    ids = [s["id"] for s in sections]
    assert "§1" in ids
    assert "§1.1" in ids
    assert "§2" in ids
    assert len(sections) >= 4


def test_regex_sections_skips_duplicates_and_junk():
    text = """
1 Intro
1 Intro
NOT A HEADING 99
random line that's not a heading but has 1 Intro embedded
""".strip()
    out = regex_sections(text)
    assert len(out) == 1
    assert out[0]["id"] == "§1"


def test_pdf_ingest_extract_text_handles_minimal_pdf():
    # A minimal valid PDF that pypdf can open. Built with pypdf itself.
    import pypdf
    import io
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    # Extract_text shouldn't raise on a blank page.
    result = pdf_ingest.extract_text(buf.getvalue())
    assert isinstance(result, str)


@pytest.mark.skipif(
    os.environ.get("QUORUM_SKIP_NETWORK", "").lower() in ("1", "true"),
    reason="network tests disabled",
)
@pytest.mark.asyncio
async def test_arxiv_fetch_withdrawn_emits_clean_error():
    """A known-bogus arXiv id should raise IngestError, not crash."""
    from app.ingest.arxiv_ingest import fetch_arxiv
    with pytest.raises(IngestError):
        await fetch_arxiv("0000.00000")
