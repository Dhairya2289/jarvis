"""Smart launcher: unified launch across apps, files, and Obsidian vault."""

from __future__ import annotations

import logging
from typing import Optional

from jarvis.config import BASE_DIR

_log = logging.getLogger(__name__)

__all__ = ["smart_launch", "SmartLauncher"]


def smart_launch(query: str) -> str:
    """
    Launch the best match for *query* across apps, files, and vault.

    Resolution order:
    1. Exact app name match → launch immediately.
    2. App search hit (via :func:`jarvis.apps.desktop.search_apps`) → launch top result.
    3. File search hit (via :func:`jarvis.universal_search`) → open with xdg-open.
    4. Vault hit → open with xdg-open.

    Returns a human-readable status string.
    """
    launcher = SmartLauncher()
    return launcher.launch(query)


class SmartLauncher:
    """
    Wraps :mod:`jarvis.apps.desktop` and :mod:`jarvis.universal_search`
    into a single launch interface.
    """

    def __init__(
        self,
        vault_path: Optional[str] = None,
    ) -> None:
        self.vault_path = vault_path or str(BASE_DIR / "obsidian")
        self._searcher = None

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def launch(self, query: str) -> str:
        """
        Resolve and launch the best match for *query*.

        Returns a status string such as ``"Launched: Firefox"`` or
        ``"[ERROR] No match found for: xyz"``.
        """
        if not query or not query.strip():
            return "[ERROR] Empty query"

        # 1 — try exact desktop app match
        result = self._launch_exact_app(query)
        if result:
            return result

        # 2 — search desktop apps
        result = self._launch_best_app(query)
        if result:
            return result

        # 3 — file/vault search
        result = self._open_best_file(query)
        if result:
            return result

        return f"[ERROR] No match found for: {query}"

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _launch_exact_app(self, name: str) -> Optional[str]:
        """Try to launch an app by exact name match."""
        try:
            from jarvis.apps.desktop import launch_app
        except ImportError as exc:
            _log.warning("apps.desktop import failed: %s", exc)
            return None

        try:
            from jarvis.apps.desktop import list_apps
        except ImportError:
            return None

        q_lower = name.strip().lower()
        for app in list_apps():
            if app.name.lower() == q_lower:
                return launch_app(app.name)
        return None

    def _launch_best_app(self, query: str) -> Optional[str]:
        """Search apps and launch the top result."""
        try:
            from jarvis.apps.desktop import search_apps, launch_app
        except ImportError as exc:
            _log.warning("apps.desktop import failed: %s", exc)
            return None

        hits = search_apps(query)
        if not hits:
            return None

        top = hits[0]
        _log.info("Smart launch: app '%s' matched query '%s'", top.name, query)
        return launch_app(top.name)

    def _open_best_file(self, query: str) -> Optional[str]:
        """Search files/vault and open the top result with xdg-open."""
        try:
            from jarvis.universal_search import UniversalSearcher
        except ImportError as exc:
            _log.warning("universal_search import failed: %s", exc)
            return None

        try:
            if self._searcher is None:
                self._searcher = UniversalSearcher(
                    scopes=["files", "vault"],
                    vault_path=self.vault_path,
                )
            results = self._searcher.search(query, limit_per_scope=3)
        except Exception as exc:
            _log.error("universal search failed: %s", exc)
            return None

        if not results:
            return None

        top = results[0]
        if top.path:
            return self._xdg_open(top.path)
        return None

    @staticmethod
    def _xdg_open(path: str) -> str:
        """Open a file/URL with xdg-open."""
        import subprocess

        try:
            subprocess.Popen(["xdg-open", path])
            _log.info("Opened: %s", path)
            return f"Opened: {path}"
        except FileNotFoundError:
            return f"[ERROR] xdg-open not found"
        except Exception as exc:
            return f"[ERROR] xdg-open failed: {exc}"