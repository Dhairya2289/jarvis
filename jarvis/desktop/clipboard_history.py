"""Clipboard history via wl-clipboard (Wayland) with SQLite fallback."""

from __future__ import annotations

import json
import logging
import sqlite3
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

from jarvis.config import BASE_DIR

_log = logging.getLogger(__name__)

__all__ = ["ClipboardHistory"]

_DB_PATH = BASE_DIR / "clipboard_history.db"
_MAX_ENTRIES = 1000


def _run_wl_paste() -> Optional[str]:
    """Get current clipboard text via wl-paste, or None if unavailable."""
    try:
        result = subprocess.run(
            ["wl-paste", "--no-spelling"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout
    except FileNotFoundError:
        _log.debug("wl-paste not available — clipboard history disabled")
    except Exception as exc:
        _log.warning("wl-paste failed: %s", exc)
    return None


class ClipboardHistory:
    """
    Stores clipboard history in SQLite, with optional live watching via
    ``wl-paste --watch``.

    Example
    -------
    >>> hist = ClipboardHistory()
    >>> hist.store("hello world")
    >>> hist.get_recent(5)
    ['hello world', ...]
    >>> hist.search("hello")
    ['hello world']
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or _DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._watcher_running = False
        self._watcher_thread: Optional[threading.Thread] = None
        self._last_content: Optional[str] = None

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def get_recent(self, n: int = 20) -> list[str]:
        """
        Return the *n* most recent clipboard entries (newest first).
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            cur = conn.execute(
                "SELECT content FROM clipboard ORDER BY id DESC LIMIT ?",
                (n,),
            )
            rows = [r[0] for r in cur.fetchall()]
            conn.close()
            return rows
        except Exception as exc:
            _log.error("get_recent failed: %s", exc)
            return []

    def search(self, query: str) -> list[str]:
        """
        Return all entries containing *query* (case-insensitive substring).
        """
        if not query:
            return self.get_recent(50)
        try:
            conn = sqlite3.connect(str(self.db_path))
            cur = conn.execute(
                "SELECT content FROM clipboard WHERE content LIKE ? ORDER BY id DESC LIMIT 100",
                (f"%{query}%",),
            )
            rows = [r[0] for r in cur.fetchall()]
            conn.close()
            return rows
        except Exception as exc:
            _log.error("search failed: %s", exc)
            return []

    def store(self, content: str) -> None:
        """Explicitly store a clipboard entry."""
        if not content or not content.strip():
            return
        content = content[:10000]  # cap at 10k chars
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute(
                "INSERT INTO clipboard(content) VALUES (?)",
                (content,),
            )
            conn.execute(
                "DELETE FROM clipboard WHERE id NOT IN (SELECT id FROM clipboard ORDER BY id DESC LIMIT ?)",
                (_MAX_ENTRIES,),
            )
            conn.commit()
            conn.close()
            _log.debug("Stored clipboard entry: %.50s", content)
        except Exception as exc:
            _log.error("store failed: %s", exc)

    def poll_once(self) -> Optional[str]:
        """
        Poll the current clipboard once and store if it has changed.

        Returns the new content if stored, else None.
        """
        content = _run_wl_paste()
        if content and content != self._last_content and content.strip():
            self._last_content = content
            self.store(content)
            return content
        return None

    def start_watcher(self, interval: float = 2.0) -> None:
        """
        Start a background thread that polls the clipboard every *interval* seconds.

        This is a simple polling approach; ``wl-paste --watch`` would be more
        efficient but is not always available.
        """
        if self._watcher_running:
            _log.warning("Watcher already running")
            return

        self._watcher_running = True

        def _poll_loop() -> None:
            while self._watcher_running:
                self.poll_once()
                time.sleep(interval)

        self._watcher_thread = threading.Thread(target=_poll_loop, daemon=True)
        self._watcher_thread.start()
        _log.info("Clipboard watcher started (poll interval=%.1fs)", interval)

    def stop_watcher(self) -> None:
        """Stop the background clipboard watcher."""
        self._watcher_running = False
        if self._watcher_thread:
            self._watcher_thread.join(timeout=5)
            self._watcher_thread = None
        _log.info("Clipboard watcher stopped")

    def count(self) -> int:
        """Return total number of entries in history."""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cur = conn.execute("SELECT COUNT(*) FROM clipboard")
            count = cur.fetchone()[0]
            conn.close()
            return count
        except Exception as exc:
            _log.error("count failed: %s", exc)
            return 0

    # ------------------------------------------------------------------ #
    # Private
    # ------------------------------------------------------------------ #

    def _init_db(self) -> None:
        """Create the SQLite table if it doesn't exist."""
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS clipboard (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    created_at REAL DEFAULT (julianday('now'))
                )
                """
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            _log.error("DB init failed: %s", exc)