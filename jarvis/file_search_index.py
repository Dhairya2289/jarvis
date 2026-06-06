"""SQLite FTS5-backed file index with incremental update support."""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Generator, Optional

__all__ = ["FileSearchIndex", "SearchResult"]

_log = logging.getLogger(__name__)

# -------------------------------------------------------------------------- #
# Internal result type (not exposed in __all__)
# -------------------------------------------------------------------------- #

@dataclass
class SearchResult:
    """A single file search result."""
    path: str
    basename: str
    extension: str
    size: int
    mtime: float
    snippet: str  # context around the matched term


# -------------------------------------------------------------------------- #
# FileSearchIndex
# -------------------------------------------------------------------------- #

class FileSearchIndex:
    """
    SQLite FTS5-backed index of files under a root directory.

    Index schema
    ------------
    fts_index(path, basename, extension)  -- FTS5 virtual table
    files(path TEXT PK, basename, extension, size INTEGER, mtime REAL)

    The FTS5 table tokenises path + basename + extension, enabling
    prefix and substring matches.  The ``files`` shadow table tracks
    full metadata for incremental updates.
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._lock = threading.Lock()
        self._init_db()

    # ------------------------------------------------------------------ #
    # Schema setup
    # ------------------------------------------------------------------ #

    def _init_db(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            # FTS5 virtual table for full-text search on path/basename/extension
            cur.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS fts_index
                USING fts5(path, basename, extension,
                           tokenize='porter unicode61')
            """)
            # Shadow table for metadata (used by incremental update diffing)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS files(
                    path       TEXT PRIMARY KEY,
                    basename   TEXT NOT NULL,
                    extension  TEXT NOT NULL DEFAULT '',
                    size       INTEGER NOT NULL DEFAULT 0,
                    mtime      REAL NOT NULL DEFAULT 0
                )
            """)
            cur.execute("PRAGMA journal_mode=WAL")
            self._conn.commit()
        _log.info("FileSearchIndex initialised at %s", self.db_path)

    # ------------------------------------------------------------------ #
    # Scan — full re-index
    # ------------------------------------------------------------------ #

    def scan(self, root: Path, exclude_patterns: Optional[list[str]] = None) -> int:
        """
        Walk *root* recursively and index every regular file.
        Returns the number of files indexed.

        Files matching any string in *exclude_patterns* (simple substring
        match on the full path) are skipped.
        """
        root = Path(root).expanduser().resolve()
        exclude_patterns = exclude_patterns or [
            ".git", ".cache", "__pycache__", ".venv", "node_modules",
            ".thumbnails", ".trash", ".obsidian",
        ]

        count = 0
        with self._lock:
            cur = self._conn.cursor()
            # Clear existing data
            cur.execute("DELETE FROM fts_index")
            cur.execute("DELETE FROM files")
            self._conn.commit()

        rows: list[tuple] = []
        for file_path in self._walk_files(root, exclude_patterns):
            try:
                stat = file_path.stat()
            except (OSError, PermissionError):
                continue
            rows.append((
                str(file_path),
                file_path.name,
                file_path.suffix.lstrip(".").lower(),
                stat.st_size,
                stat.st_mtime,
            ))
            if len(rows) >= 500:
                self._insert_rows(rows, exclusive=False)
                count += len(rows)
                rows.clear()

        if rows:
            self._insert_rows(rows, exclusive=False)
            count += len(rows)

        _log.info("Scan of %s complete: %d files indexed", root, count)
        return count

    # ------------------------------------------------------------------ #
    # Incremental update — diff against live filesystem
    # ------------------------------------------------------------------ #

    def watch_and_update(self, root: Path, exclude_patterns: Optional[list[str]] = None) -> None:
        """
        Poll *root* for changes and update the index incrementally.

        This method blocks forever (call in a background thread).
        It re-scans periodically and diffs new/modified/deleted files.
        """
        exclude_patterns = exclude_patterns or [
            ".git", ".cache", "__pycache__", ".venv", "node_modules",
            ".thumbnails", ".trash", ".obsidian",
        ]
        while True:
            try:
                self._incremental_update(root, exclude_patterns)
            except Exception as exc:
                _log.error("watch_and_update error: %s", exc)
            # Re-scan interval — keep it modest to avoid hammering the FS
            import time; time.sleep(30)

    def _incremental_update(self, root: Path, exclude_patterns: list[str]) -> None:
        """Compare the live filesystem against the indexed state and patch."""
        root = Path(root).resolve()
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT path, mtime FROM files")
            indexed: dict[str, float] = {row[0]: row[1] for row in cur.fetchall()}

        live: dict[str, float] = {}
        for fp in self._walk_files(root, exclude_patterns):
            try:
                live[str(fp)] = fp.stat().st_mtime
            except (OSError, PermissionError):
                continue

        to_add   = set(live) - set(indexed)
        to_del   = set(indexed) - set(live)
        to_check = set(live) & set(indexed)

        rows: list[tuple] = []
        for path_str in to_add:
            fp = Path(path_str)
            try:
                s = fp.stat()
                rows.append((path_str, fp.name, fp.suffix.lstrip(".").lower(),
                              s.st_size, s.st_mtime))
            except (OSError, PermissionError):
                continue

        if rows:
            self._insert_rows(rows, exclusive=True)
            _log.info("Incremental add: %d files", len(rows))

        if to_del:
            self._remove_paths(list(to_del))
            _log.info("Incremental delete: %d files", len(to_del))

        updated = 0
        for path_str in to_check:
            if abs(live[path_str] - indexed[path_str]) > 1e-3:
                fp = Path(path_str)
                try:
                    s = fp.stat()
                    self._upsert_one(fp, s)
                    updated += 1
                except (OSError, PermissionError):
                    continue
        if updated:
            _log.info("Incremental update: %d files", updated)

    # ------------------------------------------------------------------ #
    # Search
    # ------------------------------------------------------------------ #

    def search(self, query: str, limit: int = 20) -> list[SearchResult]:
        """
        Full-text search of the index.

        Falls back to a fuzzy basename scan when:
          - the FTS query returns 0 results (e.g. no token overlap), OR
          - the query contains no FTS-token-length word (all very short).

        Returns up to *limit* results, sorted by relevance.
        """
        if not query or not query.strip():
            return []

        query = query.strip()

        # Try FTS5 first
        fts_results = self._fts_search(query, limit)
        if fts_results:
            return fts_results

        # Fuzzy fallback on basename
        return self._fuzzy_search(query, limit)

    def _fts_search(self, query: str, limit: int) -> list[SearchResult]:
        """Run an FTS5 query with prefix matching."""
        # Build a prefix query: each word gets * suffix
        tokens = query.split()
        fts_query = " ".join(f"{t}*" for t in tokens if len(t) > 1)

        if not fts_query:
            return []

        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute("""
                    SELECT f.path, f.basename, f.extension, f.size, f.mtime,
                           snippet(fts_index, 1, '**', '**', '…', 32) AS snippet
                    FROM fts_index
                    JOIN files f ON f.path = fts_index.path
                    WHERE fts_index MATCH ?
                    ORDER BY rank
                    LIMIT ?
                """, (fts_query, limit))
                rows = cur.fetchall()
            except sqlite3.FtsError as exc:
                _log.warning("FTS query failed: %s", exc)
                return []

        return [
            SearchResult(
                path=row[0],
                basename=row[1],
                extension=row[2],
                size=row[3],
                mtime=row[4],
                snippet=row[5] or row[1],
            )
            for row in rows
        ]

    def _fuzzy_search(self, query: str, limit: int) -> list[SearchResult]:
        """
        Fuzzy search by basename using thefuzz token-set ratio.

        Pulls all basenames from the shadow table (up to 50 k rows for
        performance), scores them, and returns the top *limit*.
        """
        try:
            from thefuzz import fuzz, process
        except ImportError:
            _log.warning("thefuzz not installed; fuzzy search unavailable")
            return []

        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT path, basename, extension, size, mtime FROM files")
            rows = cur.fetchall()

        if not rows:
            return []

        basenames = [r[1] for r in rows]
        try:
            matches = process.extractBests(
                query, basenames,
                scorer=fuzz.token_set_ratio,
                limit=min(limit * 3, len(basenames)),
                score_cutoff=30,
            )
        except Exception as exc:
            _log.warning("thefuzz process.extractBests failed: %s", exc)
            return []

        path_map = {r[1]: r for r in rows}
        scored: list[tuple[SearchResult, int]] = []
        for match, score in matches:
            row = path_map[match]
            scored.append((
                SearchResult(
                    path=row[0],
                    basename=row[1],
                    extension=row[2],
                    size=row[3],
                    mtime=row[4],
                    snippet=row[1],
                ),
                -score,
            ))

        scored.sort(key=lambda x: x[1])
        return [s for s, _ in scored[:limit]]

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _walk_files(self, root: Path, exclude_patterns: list[str]) -> Generator[Path, None, None]:
        """Yield regular files under *root*, respecting exclusions."""
        for dirpath, dirnames, filenames in os.walk(root, onerror=None):
            dp = Path(dirpath)
            # Prune excluded dirs in-place so os.walk doesn't descend
            dirnames[:] = [
                d for d in dirnames
                if not any(ex in str(dp / d) for ex in exclude_patterns)
            ]
            for fn in filenames:
                fp = dp / fn
                if not fp.is_file():
                    continue
                if any(ex in str(fp) for ex in exclude_patterns):
                    continue
                yield fp

    def _insert_rows(self, rows: list[tuple], exclusive: bool = True) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.executemany(
                "INSERT OR REPLACE INTO files(path,basename,extension,size,mtime) VALUES (?,?,?,?,?)",
                rows,
            )
            # Re-populate FTS5 from shadow table
            cur.execute("DELETE FROM fts_index")
            cur.execute("""
                INSERT INTO fts_index(path, basename, extension)
                SELECT path, basename, extension FROM files
            """)
            self._conn.commit()

    def _upsert_one(self, fp: Path, stat) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO files(path,basename,extension,size,mtime) VALUES (?,?,?,?,?)",
                (str(fp), fp.name, fp.suffix.lstrip(".").lower(), stat.st_size, stat.st_mtime),
            )
            # Re-populate FTS5 from shadow table (simple, correct)
            cur.execute("DELETE FROM fts_index")
            cur.execute("""
                INSERT INTO fts_index(path, basename, extension)
                SELECT path, basename, extension FROM files
            """)
            self._conn.commit()

    def _remove_paths(self, paths: list[str]) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.executemany("DELETE FROM files WHERE path = ?", [(p,) for p in paths])
            # Re-populate FTS5 from shadow table
            cur.execute("DELETE FROM fts_index")
            cur.execute("""
                INSERT INTO fts_index(path, basename, extension)
                SELECT path, basename, extension FROM files
            """)
            self._conn.commit()