"""Tests for PDF ingestion module."""

from __future__ import annotations

from pathlib import Path

import pypdf
import pytest

from jarvis.pdf_ingestion import PDFIngestion, _sanitize_filename, _build_markdown_content


def test_sanitize_filename():
    """Sanitize removes problematic characters."""
    # _sanitize_filename operates on pdf_path.stem (no extension)
    assert _sanitize_filename("My File<test>") == "My File_test_"
    assert _sanitize_filename("normal_file") == "normal_file"


def test_build_markdown_content(tmp_path: Path):
    """Markdown output has frontmatter and page sections."""
    pages = ["Page one content.", "Page two content."]
    content = _build_markdown_content(
        "Test Doc", pages, tmp_path / "source.pdf"
    )
    assert content.startswith("---")
    assert "title: Test Doc" in content
    assert "source:" in content
    assert "## Page 1" in content
    assert "## Page 2" in content
    assert "Page one content." in content
    assert "pdf-note" in content


def test_ingest_creates_obsidian_note(tmp_path: Path):
    """Ingesting a PDF creates a markdown file with frontmatter."""
    # Create a minimal PDF programmatically
    pdf_path = tmp_path / "test_doc.pdf"
    _create_minimal_pdf(pdf_path)

    # Use tmp vault path for test
    vault = tmp_path / "vault"
    vault.mkdir()
    ingestor = PDFIngestion(vault_path=vault)

    md_path = ingestor.ingest(pdf_path, folder="test_pdfs")

    assert md_path.exists()
    text = md_path.read_text()
    assert "---" in text
    assert "test_doc" in text.lower()
    assert "tags:" in text
    assert "pdf-note" in text
    assert "Page 1" in text


def test_batch_ingest_multiple_pdfs(tmp_path: Path):
    """batch_ingest processes all PDFs in a directory."""
    # Create two PDFs
    pdf1 = tmp_path / "doc1.pdf"
    pdf2 = tmp_path / "doc2.pdf"
    _create_minimal_pdf(pdf1)
    _create_minimal_pdf(pdf2)

    pdfs_dir = tmp_path / "pdfs"
    pdfs_dir.mkdir()
    pdf1.rename(pdfs_dir / "doc1.pdf")
    pdf2.rename(pdfs_dir / "doc2.pdf")

    vault = tmp_path / "vault"
    vault.mkdir()
    ingestor = PDFIngestion(vault_path=vault)

    results = ingestor.batch_ingest(pdfs_dir)

    assert len(results) == 2
    assert all(r.suffix == ".md" for r in results)


def test_ingest_nonexistent_raises(tmp_path: Path):
    """Ingesting a nonexistent PDF raises FileNotFoundError."""
    vault = tmp_path / "vault"
    vault.mkdir()
    ingestor = PDFIngestion(vault_path=vault)

    with pytest.raises(FileNotFoundError):
        ingestor.ingest(tmp_path / "nonexistent.pdf")


def _create_minimal_pdf(output_path: Path) -> None:
    """Create a minimal valid PDF with one page containing text."""
    _write_simple_pdf_with_text(output_path, "Test page content for PDF ingestion.")


def _write_simple_pdf_with_text(output_path: Path, text: str) -> None:
    """Write a minimal PDF containing the given text."""
    # Minimal valid PDF structure
    content = f"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj
4 0 obj
<< /Length {len(text) + 50} >>
stream
BT
/F1 12 Tf
100 700 Td
({text}) Tj
ET
endstream
endobj
5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000266 00000 n
0000000400 00000 n
trailer
<< /Size 6 /Root 1 0 R >>
startxref
{450 + len(text)}
%%EOF
"""
    output_path.write_bytes(content.encode("latin-1", errors="replace"))