"""Download Organizer — Auto-sort ~/Downloads by MIME type/extension."""

from __future__ import annotations

import logging
import mimetypes
import shutil
from dataclasses import dataclass
from pathlib import Path

from jarvis.config import BASE_DIR

log = logging.getLogger(__name__)


# Category definitions: folder name -> extensions (lowercase, no dot)
CATEGORIES: dict[str, set[str]] = {
    "Images": {
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp",
        ".tiff", ".tif", ".ico", ".heic", ".heif", ".avif",
    },
    "Documents": {
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".odt", ".ods", ".odp", ".rtf", ".txt", ".md", ".csv",
        ".epub", ".fb2", ".djvu",
    },
    "Archives": {
        ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
        ".iso", ".dmg", ".deb", ".rpm",
    },
    "Media": {
        ".mp3", ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flac",
        ".ogg", ".wav", ".aac", ".m4a", ".webm", ".flv",
    },
    "Code": {
        ".py", ".js", ".ts", ".html", ".css", ".json", ".xml",
        ".yaml", ".yml", ".toml", ".sh", ".bash", ".zsh",
        ".c", ".cpp", ".h", ".hpp", ".java", ".go", ".rs",
        ".rb", ".php", ".swift", ".kt", ".scala", ".sql",
    },
}

# Fallback category for unclassified files
OTHER_CATEGORY = "Other"


@dataclass
class OrganizeResult:
    """Result of an organize operation."""

    category: str
    files_moved: int
    destination: Path


def _guess_mime(path: Path) -> str:
    """Guess MIME type from a file path."""
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "application/octet-stream"


def _get_category(filename: str, mime: str) -> str:
    """Determine the category for a file based on extension and MIME type."""
    ext = filename.lower()
    if "." in ext:
        ext = "." + ext.rsplit(".", 1)[-1]
    else:
        ext = ""

    # Check extension first
    for category, extensions in CATEGORIES.items():
        if ext in extensions:
            return category

    # Fallback: check MIME type
    if mime.startswith("image/"):
        return "Images"
    elif mime.startswith("video/"):
        return "Media"
    elif mime.startswith("audio/"):
        return "Media"
    elif mime.startswith("text/"):
        return "Documents"
    elif mime == "application/pdf":
        return "Documents"
    elif "document" in mime or "spreadsheet" in mime or "presentation" in mime:
        return "Documents"
    elif "archive" in mime or "compressed" in mime:
        return "Archives"

    return OTHER_CATEGORY


def suggested_tags(filename: str, mime: str) -> list[str]:
    """Suggest tags based on filename and MIME type.

    Args:
        filename: The file's basename.
        mime: The guessed MIME type.

    Returns:
        List of suggested tags.
    """
    tags: list[str] = []
    ext = filename.lower().rpartition(".")[-1] if "." in filename else ""

    # Add extension as tag
    if ext:
        tags.append(ext)

    # Add mime category tags
    if mime.startswith("image/"):
        tags.append("image")
    elif mime.startswith("video/"):
        tags.append("video")
    elif mime.startswith("audio/"):
        tags.append("audio")
    elif mime.startswith("text/"):
        tags.append("text")

    return list(dict.fromkeys(tags))  # deduplicate preserve order


class DownloadOrganizer:
    """Auto-sort downloads directory by MIME type and extension."""

    def __init__(self, downloads_dir: Path | None = None) -> None:
        self.downloads_dir = downloads_dir or Path.home() / "Downloads"
        self.stats: dict[str, int] = {}

    def organize(self, dry_run: bool = False) -> dict[str, int]:
        """Organize files in the downloads directory.

        Args:
            dry_run: If True, only simulate without moving files.

        Returns:
            Dict mapping category names to file counts moved.
        """
        if not self.downloads_dir.is_dir():
            log.error("Downloads directory not found: %s", self.downloads_dir)
            return {}

        self.stats = {cat: 0 for cat in CATEGORIES}
        self.stats[OTHER_CATEGORY] = 0

        files = [f for f in self.downloads_dir.iterdir() if f.is_file()]
        for file_path in files:
            mime = _guess_mime(file_path)
            category = _get_category(file_path.name, mime)
            dest_dir = self.downloads_dir / category
            dest_path = dest_dir / file_path.name

            if dry_run:
                log.info(
                    "[DRY RUN] Would move %s -> %s (%s)",
                    file_path.name,
                    category,
                    mime,
                )
            else:
                dest_dir.mkdir(parents=True, exist_ok=True)
                if dest_path.exists():
                    base = file_path.stem
                    ext = file_path.suffix
                    counter = 1
                    while dest_path.exists():
                        dest_path = dest_dir / f"{base}_{counter}{ext}"
                        counter += 1
                shutil.move(str(file_path), str(dest_path))
                log.info("Moved %s -> %s", file_path.name, category)

            self.stats[category] += 1

        return self.stats

    def get_stats(self) -> dict[str, int]:
        """Return the stats from the last organize call."""
        return self.stats.copy() if self.stats else {cat: 0 for cat in CATEGORIES}


__all__ = ["DownloadOrganizer", "suggested_tags", "OrganizeResult"]