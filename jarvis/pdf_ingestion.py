"""PDF Ingestion — Extract text from PDFs into Obsidian markdown notes."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pypdf

from jarvis.config import BASE_DIR

log = logging.getLogger(__name__)


@dataclass
class IngestResult:
    """Result of a PDF ingestion operation."""

    pdf_path: Path
    markdown_path: Path
    pages: int
    word_count: int


def _sanitize_filename(name: str) -> str:
    """Sanitize a string for use as a filename."""
    return re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "_", name).strip()


def _extract_text(pdf_path: Path) -> tuple[list[str], int]:
    """Extract text from all pages of a PDF.

    Returns (pages_text, total_word_count)
    """
    pages: list[str] = []
    total_words = 0
    try:
        reader = pypdf.PdfReader(str(pdf_path))
        for page in reader.pages:
            text = page.extract_text() or ""
            pages.append(text)
            total_words += len(text.split())
    except Exception as e:
        log.error("Failed to extract text from %s: %s", pdf_path, e)
        raise
    return pages, total_words


def _build_markdown_content(
    title: str,
    pages: list[str],
    pdf_path: Path,
    metadata: dict | None = None,
) -> str:
    """Build Obsidian-flavored markdown with frontmatter."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "---",
        f"title: {title}",
        f"created: {now}",
        f"modified: {now}",
        f"source: {pdf_path}",
        "tags: [pdf, ingested]",
        "type: pdf-note",
    ]
    if metadata:
        for k, v in metadata.items():
            lines.append(f"{k}: {v}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {title}")
    lines.append("")
    for i, page_text in enumerate(pages, 1):
        lines.append(f"## Page {i}")
        lines.append("")
        lines.append(page_text.strip())
        lines.append("")
    return "\n".join(lines)


class PDFIngestion:
    """Ingest PDF files into Obsidian markdown notes."""

    def __init__(self, vault_path: Path | None = None) -> None:
        self.vault_path = vault_path or (BASE_DIR / "obsidian" / "JARVIS")
        self.vault_path.mkdir(parents=True, exist_ok=True)

    def ingest(self, pdf_path: Path, folder: str = "pdfs") -> Path:
        """Ingest a single PDF into an Obsidian note.

        Args:
            pdf_path: Path to the PDF file.
            folder: Target folder within the vault (default: "pdfs").

        Returns:
            Path to the created markdown file.
        """
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        title = _sanitize_filename(pdf_path.stem)
        pages, word_count = _extract_text(pdf_path)

        metadata = {
            "pages": len(pages),
            "word_count": word_count,
        }
        content = _build_markdown_content(title, pages, pdf_path, metadata)

        target_folder = self.vault_path / folder
        target_folder.mkdir(parents=True, exist_ok=True)
        md_path = target_folder / f"{title}.md"

        if md_path.exists():
            log.warning("Overwriting existing note: %s", md_path)
        md_path.write_text(content, encoding="utf-8")

        log.info(
            "Ingested %s (%d pages, %d words) -> %s",
            pdf_path.name,
            len(pages),
            word_count,
            md_path,
        )
        return md_path

    def batch_ingest(
        self,
        dir_path: Path,
        folder: str = "pdfs",
        glob_pattern: str = "*.pdf",
    ) -> list[Path]:
        """Ingest all PDFs from a directory.

        Args:
            dir_path: Directory containing PDF files.
            folder: Target folder within the vault.
            glob_pattern: Glob pattern to match PDFs.

        Returns:
            List of paths to created markdown files.
        """
        if not dir_path.is_dir():
            raise NotADirectoryError(f"Not a directory: {dir_path}")

        results: list[Path] = []
        for pdf_path in sorted(dir_path.glob(glob_pattern)):
            if pdf_path.is_file():
                try:
                    result = self.ingest(pdf_path, folder=folder)
                    results.append(result)
                except Exception as e:
                    log.error("Failed to ingest %s: %s", pdf_path, e)
        return results


__all__ = ["PDFIngestion", "IngestResult"]