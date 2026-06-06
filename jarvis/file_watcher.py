"""Watch the notes directory and ingest changed Markdown/text files into memory.
Also watch Downloads and auto-trigger organize_downloads on new files.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Final

from jarvis.config import NOTES_DIR
from jarvis.episodic_memory import store_successful_task

_log = logging.getLogger(__name__)

WATCH_DIR: Final[Path] = Path(NOTES_DIR).expanduser()
DOWNLOADS_DIR: Final[Path] = Path.home() / "Downloads"
_POLL_INTERVAL: Final[int] = 5
_ALLOWED_EXTS: Final[set[str]] = {".txt", ".md"}


def _ingest(path: Path) -> None:
    """Read *path* into episodic memory if it is a supported text file."""
    if path.suffix.lower() not in _ALLOWED_EXTS or not path.exists():
        return
    try:
        content = path.read_text(errors="replace")[:8000]
    except OSError:
        _log.debug("Could not read %s", path)
        return
    if not content.strip():
        return
    try:
        store_successful_task(f"User note: {path.name}", [content])
        _log.info("Memory updated from %s", path)
    except Exception:
        _log.error("Failed to store note %s", path, exc_info=True)


def _shutil_which(cmd: str) -> str | None:
    return shutil.which(cmd)


def _on_downloads_change(path: Path) -> None:
    """Handle a new file in Downloads: wait 2s then organize."""
    if path.is_dir():
        return
    _log.info("Download detected: %s — waiting 2s", path.name)
    time.sleep(2)
    try:
        from jarvis.download_organizer import DownloadOrganizer
        result = DownloadOrganizer(downloads_dir=DOWNLOADS_DIR).organize()
        _log.info("Organized downloads: %s", result)
    except Exception:
        _log.error("Failed to organize downloads", exc_info=True)


def _watch_downloads() -> None:
    """Watch Downloads for new files and auto-organize."""
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    _log.info("Watching Downloads: %s", DOWNLOADS_DIR)

    if not _shutil_which("inotifywait"):
        _log.info("inotifywait not found; Downloads watcher disabled")
        return

    process = subprocess.Popen(
        [
            "inotifywait",
            "-m",
            "-e",
            "create,moved_to",
            "--format",
            "%w%f",
            str(DOWNLOADS_DIR),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert process.stdout is not None
    for line in iter(process.stdout.readline, ""):
        _on_downloads_change(Path(line.strip()))


def watch_files() -> None:
    """Start watching *WATCH_DIR* using inotifywait if available, otherwise poll."""
    WATCH_DIR.mkdir(parents=True, exist_ok=True)
    _log.info("Watching %s", WATCH_DIR)

    if not _shutil_which("inotifywait"):
        _log.info("inotifywait not found; using polling fallback")
        _poll_files()
        return

    process = subprocess.Popen(
        [
            "inotifywait",
            "-m",
            "-e",
            "create,modify,moved_to",
            "--format",
            "%w%f",
            str(WATCH_DIR),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert process.stdout is not None
    for line in iter(process.stdout.readline, ""):
        _ingest(Path(line.strip()))


def _poll_files() -> None:
    seen: dict[Path, float] = {}
    while True:
        for path in WATCH_DIR.glob("**/*"):
            if not path.is_file() or path.suffix.lower() not in _ALLOWED_EXTS:
                continue
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if seen.get(path) != mtime:
                seen[path] = mtime
                _ingest(path)
        time.sleep(_POLL_INTERVAL)


def start() -> None:
    """Start all file watchers (notes + downloads) in background threads."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    threads = [
        threading.Thread(target=watch_files, daemon=True),
        threading.Thread(target=_watch_downloads, daemon=True),
    ]
    for t in threads:
        t.start()
    _log.info("File watchers started")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        _log.info("Shutting down watchers")


if __name__ == "__main__":
    start()


__all__ = ["watch_files", "_watch_downloads", "_ingest", "start"]
