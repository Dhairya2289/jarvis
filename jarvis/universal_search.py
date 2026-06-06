"""Universal fuzzy search across files, desktop apps, and Obsidian vault."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from jarvis.config import BASE_DIR

_log = logging.getLogger(__name__)

__all__ = ["universal_search", "SearchResult", "UniversalSearcher"]

# -------------------------------------------------------------------------- #
# Data types
# -------------------------------------------------------------------------- #

@dataclass
class SearchResult:
    """
    A unified search result from any scope.

    Attributes
    ----------
    kind : str
        One of: ``file``, ``app``, ``vault``.
    title : str
        Human-readable name or title of the result.
    path : str | None
        Primary path or identifier (file path, app exec, vault note path).
    score : float
        Relevance score in [0, 100], higher = more relevant.
    meta : dict
        Additional metadata specific to the kind.
    """
    kind: str
    title: str
    path: str | None
    score: float
    meta: dict = field(default_factory=dict)


# -------------------------------------------------------------------------- #
# UniversalSearcher
# -------------------------------------------------------------------------- #

class UniversalSearcher:
    """
    Unified search across multiple scopes with configurable backends.

    Parameters
    ----------
    scopes : list[str] | None
        Scopes to search.  ``None`` means all scopes:
        ``["files", "apps", "vault"]``.
    index_path : Path | None
        Path for the file-search SQLite index.
        Defaults to ``~/.jarvis/file_index.db``.
    vault_path : Path | None
        Path to the Obsidian vault.
        Defaults to ``~/.jarvis/obsidian``.
    """

    def __init__(
        self,
        scopes: Optional[list[str]] = None,
        index_path: Optional[Path] = None,
        vault_path: Optional[Path] = None,
    ) -> None:
        self.scopes = set(scopes) if scopes else {"files", "apps", "vault"}
        self.index_path = index_path or (BASE_DIR / "file_index.db")
        self.vault_path = vault_path or (BASE_DIR / "obsidian")
        self._file_index: "FileSearchIndex | None" = None

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def search(self, query: str, limit_per_scope: int = 10) -> list[SearchResult]:
        """
        Search across all configured scopes and merge results.

        Parameters
        ----------
        query : str
            Search query string.
        limit_per_scope : int
            Maximum results to retrieve from each scope before merging.
            The final list is capped at ``limit_per_scope * len(scopes)``.

        Returns
        -------
        list[SearchResult]
            Flattened, de-duplicated results sorted by descending score.
        """
        if not query or not query.strip():
            return []

        results: list[SearchResult] = []

        if "files" in self.scopes:
            results.extend(self._search_files(query, limit_per_scope))

        if "apps" in self.scopes:
            results.extend(self._search_apps(query, limit_per_scope))

        if "vault" in self.scopes:
            results.extend(self._search_vault(query, limit_per_scope))

        # Sort descending by score, drop duplicates (prefer higher score)
        seen: dict[str, SearchResult] = {}
        for r in sorted(results, key=lambda x: -x.score):
            key = (r.kind, r.title.lower())
            if key not in seen:
                seen[key] = r

        merged = list(seen.values())
        merged.sort(key=lambda x: -x.score)
        return merged

    # ------------------------------------------------------------------ #
    # Scope implementations
    # ------------------------------------------------------------------ #

    def _search_files(self, query: str, limit: int) -> list[SearchResult]:
        """Search the file index."""
        try:
            from jarvis.file_search_index import FileSearchIndex
        except ImportError as exc:
            _log.warning("file_search_index import failed: %s", exc)
            return []

        if self._file_index is None:
            self._file_index = FileSearchIndex(self.index_path)

        try:
            hits = self._file_index.search(query, limit)
        except Exception as exc:
            _log.error("file index search failed: %s", exc)
            return []

        return [
            SearchResult(
                kind="file",
                title=hit.basename,
                path=hit.path,
                score=self._file_score(hit, query),
                meta={
                    "size": hit.size,
                    "extension": hit.extension,
                    "mtime": hit.mtime,
                    "snippet": hit.snippet,
                },
            )
            for hit in hits
        ]

    def _search_apps(self, query: str, limit: int) -> list[SearchResult]:
        """Search desktop applications via jarvis.apps.desktop."""
        try:
            from jarvis.apps.desktop import search_apps, DesktopApp
        except ImportError as exc:
            _log.warning("apps.desktop import failed: %s", exc)
            return []

        try:
            apps: list[DesktopApp] = search_apps(query)
        except Exception as exc:
            _log.error("app search failed: %s", exc)
            return []

        results: list[SearchResult] = []
        for app in apps[:limit]:
            score = self._app_score(app, query)
            results.append(SearchResult(
                kind="app",
                title=app.name,
                path=app.exec,
                score=score,
                meta={
                    "categories": app.categories,
                    "comment": app.comment,
                    "keywords": app.keywords,
                    "terminal": app.terminal,
                },
            ))

        # Sort by score descending
        results.sort(key=lambda x: -x.score)
        return results[:limit]

    def _search_vault(self, query: str, limit: int) -> list[SearchResult]:
        """Search the Obsidian vault via FTS-like basename matching."""
        vault = Path(self.vault_path)
        if not vault.exists():
            _log.debug("Vault path does not exist: %s", vault)
            return []

        try:
            import os as _os
            from thefuzz import fuzz as _fuzz

            note_files: list[SearchResult] = []
            q_lower = query.lower()

            # Walk vault recursively (limit scan for performance)
            count = 0
            max_scan = 10_000
            for dirpath, _, filenames in _os.walk(vault):
                # Skip Obsidian internals
                if ".obsidian" in dirpath or "__pycache__" in dirpath:
                    continue
                for fn in filenames:
                    if not fn.endswith(".md"):
                        continue
                    count += 1
                    if count > max_scan:
                        break
                    note_path = Path(dirpath) / fn
                    # Simple FTS on note basename
                    bn = fn[:-3]  # strip .md
                    if q_lower in bn.lower():
                        score = 80 + min(20, 10 * (len(q_lower) // 2))
                    else:
                        try:
                            score = _fuzz.token_set_ratio(q_lower, bn.lower())
                        except Exception:
                            score = 0
                    if score > 25:
                        note_files.append(SearchResult(
                            kind="vault",
                            title=bn,
                            path=str(note_path),
                            score=float(score),
                            meta={"extension": "md"},
                        ))
                if count > max_scan:
                    break

            note_files.sort(key=lambda x: -x.score)
            return note_files[:limit]

        except ImportError as exc:
            _log.warning("thefuzz not available for vault search: %s", exc)
            return []

    # ------------------------------------------------------------------ #
    # Scoring helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _file_score(hit: "FileSearchIndex._SearchResult", query: str) -> float:
        """
        Score a file hit in [0, 100].

        Uses thefuzz token_set_ratio against the basename when the query
        doesn't exactly match the name.
        """
        try:
            from thefuzz import fuzz as _fuzz
            basename = hit.basename.lower()
            q = query.lower()
            if q in basename:
                base = 70 + min(20, 20 * (len(q) / max(len(basename), 1)))
            else:
                base = _fuzz.token_set_ratio(q, basename) * 0.9
            return min(100.0, base)
        except ImportError:
            return 50.0

    @staticmethod
    def _app_score(app: "DesktopApp", query: str) -> float:
        """Score a desktop app hit."""
        try:
            from thefuzz import fuzz as _fuzz
            q = query.lower()
            name_score = _fuzz.token_set_ratio(q, app.name.lower())
            comment_score = _fuzz.token_set_ratio(q, app.comment.lower()) if app.comment else 0
            kw_scores = [
                _fuzz.token_set_ratio(q, k.lower()) for k in app.keywords
            ]
            best_kw = max(kw_scores) if kw_scores else 0
            return max(name_score, comment_score * 0.6, best_kw * 0.7)
        except ImportError:
            # Fallback: substring match
            q = query.lower()
            if q in app.name.lower():
                return 80.0
            return 30.0


# -------------------------------------------------------------------------- #
# Module-level convenience function
# -------------------------------------------------------------------------- #

def universal_search(
    query: str,
    scopes: Optional[list[str]] = None,
    limit_per_scope: int = 10,
) -> list[SearchResult]:
    """
    Convenience wrapper around :class:`UniversalSearcher`.

    Searches across *scopes* (default: all) and returns merged results.

    Parameters
    ----------
    query : str
        Search query.
    scopes : list[str] | None
        Scopes to search.  One or more of ``["files", "apps", "vault"]``.
        ``None`` means all three.
    limit_per_scope : int
        Maximum results per scope before merging.

    Returns
    -------
    list[SearchResult]
        Sorted by descending score.

    Example
    -------
    >>> results = universal_search("obsidian", scopes=["files", "apps"])
    >>> for r in results:
    ...     print(r.kind, r.title, r.score)
    """
    searcher = UniversalSearcher(scopes=scopes)
    return searcher.search(query, limit_per_scope=limit_per_scope)