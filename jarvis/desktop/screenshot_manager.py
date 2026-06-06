"""Screenshot manager: organize ~/Pictures/Screenshots into dated folders."""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from jarvis.config import BASE_DIR

_log = logging.getLogger(__name__)

DEFAULT_SCREENSHOT_DIR = Path.home() / "Pictures" / "Screenshots"
ARCHIVE_DIR = BASE_DIR / "screenshots_archive"
MAX_AGE_DAYS = 30

__all__ = ["ScreenshotManager"]


class ScreenshotManager:
    """
    Organise screenshots into ``~/Pictures/Screenshots/YYYY-MM/`` folders
    and optionally archive old ones.

    Example
    -------
    >>> mgr = ScreenshotManager()
    >>> mgr.organize()          # move loose files into date folders
    >>> mgr.archive(keep_days=30)  # move files older than 30 days to archive
    >>> mgr.recent(10)
    """

    def __init__(
        self,
        screenshot_dir: Optional[Path] = None,
        archive_dir: Optional[Path] = None,
    ) -> None:
        self.screenshot_dir = screenshot_dir or DEFAULT_SCREENSHOT_DIR
        self.archive_dir = archive_dir or ARCHIVE_DIR
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    def organize(self) -> dict[str, int]:
        """
        Scan ``screenshot_dir`` for loose screenshot files and move each
        into ``screenshot_dir/YYYY-MM/`` based on its mtime.

        Returns a summary dict with keys: ``moved``, ``skipped``, ``errors``.
        """
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

        moved = 0
        skipped = 0
        errors = 0

        for path in self.screenshot_dir.iterdir():
            if path.is_dir():
                continue  # skip existing date folders
            if not path.is_file():
                continue

            if self._is_screenshot(path):
                try:
                    date_folder = self._date_folder_for(path)
                    date_folder.mkdir(parents=True, exist_ok=True)
                    dest = date_folder / path.name
                    # Avoid collisions
                    if dest.exists():
                        dest = self._unique_dest(dest)
                    shutil.move(str(path), str(dest))
                    moved += 1
                    _log.debug("Moved screenshot %s -> %s", path.name, date_folder.name)
                except Exception as exc:
                    _log.error("Failed to move %s: %s", path, exc)
                    errors += 1
            else:
                skipped += 1

        _log.info("Screenshot organize: moved=%d, skipped=%d, errors=%d", moved, skipped, errors)
        return {"moved": moved, "skipped": skipped, "errors": errors}

    def archive(self, keep_days: int = MAX_AGE_DAYS) -> int:
        """
        Move screenshot files older than *keep_days* into ``archive_dir``.

        Returns the number of files archived.
        """
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        cutoff = datetime.now() - timedelta(days=keep_days)
        archived = 0

        for date_folder in sorted(self.screenshot_dir.iterdir()):
            if not date_folder.is_dir():
                continue
            if not self._looks_like_date_folder(date_folder.name):
                continue

            for path in date_folder.iterdir():
                if not path.is_file():
                    continue
                try:
                    mtime = datetime.fromtimestamp(path.stat().st_mtime)
                    if mtime < cutoff:
                        year_month = date_folder.name  # "YYYY-MM"
                        archive_year_dir = self.archive_dir / year_month
                        archive_year_dir.mkdir(parents=True, exist_ok=True)
                        dest = archive_year_dir / path.name
                        if dest.exists():
                            dest = self._unique_dest(dest)
                        shutil.move(str(path), str(dest))
                        archived += 1
                        _log.debug("Archived %s", path.name)
                except Exception as exc:
                    _log.error("Failed to archive %s: %s", path, exc)

        _log.info("Archived %d old screenshots", archived)
        return archived

    def recent(self, n: int = 10) -> list[Path]:
        """
        Return the *n* most recent screenshot files across all date folders.
        """
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

        all_files: list[tuple[datetime, Path]] = []

        for date_folder in self.screenshot_dir.iterdir():
            if not date_folder.is_dir():
                continue
            for path in date_folder.iterdir():
                if not path.is_file():
                    continue
                try:
                    mtime = datetime.fromtimestamp(path.stat().st_mtime)
                    all_files.append((mtime, path))
                except Exception:
                    pass

        all_files.sort(key=lambda x: -x[0].timestamp())
        return [p for _, p in all_files[:n]]

    def count(self) -> int:
        """Return total number of screenshot files."""
        total = 0
        for date_folder in self.screenshot_dir.iterdir():
            if date_folder.is_dir():
                total += sum(1 for p in date_folder.iterdir() if p.is_file())
        return total

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _is_screenshot(path: Path) -> bool:
        """Heuristic: is this a screenshot file?"""
        exts = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
        name_lower = path.name.lower()
        return path.suffix.lower() in exts or "screenshot" in name_lower or "shot" in name_lower

    @staticmethod
    def _looks_like_date_folder(name: str) -> bool:
        """Check if folder name looks like YYYY-MM."""
        return bool(__import__("re").match(r"^\d{4}-\d{2}$", name))

    def _date_folder_for(self, path: Path) -> Path:
        """Return the YYYY-MM date-folder path for a file, based on mtime."""
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        return self.screenshot_dir / mtime.strftime("%Y-%m")

    @staticmethod
    def _unique_dest(dest: Path) -> Path:
        """Return a unique destination path by appending a counter."""
        if not dest.exists():
            return dest
        stem = dest.stem
        suffix = dest.suffix
        parent = dest.parent
        counter = 1
        while True:
            candidate = parent / f"{stem}_{counter}{suffix}"
            if not candidate.exists():
                return candidate
            counter += 1