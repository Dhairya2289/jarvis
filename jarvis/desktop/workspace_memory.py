"""Workspace memory: snapshot/restore Hyprland workspaces via hyprctl."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Optional

from jarvis.config import BASE_DIR

_log = logging.getLogger(__name__)

SNAPSHOT_FILE = BASE_DIR / "workspace_snapshot.json"


def _run_hyprctl(args: list[str]) -> Optional[dict]:
    """Run hyprctl and return parsed JSON, or None on failure."""
    try:
        result = subprocess.run(
            ["hyprctl"] + args,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            _log.warning("hyprctl %s returned %d: %s", args, result.returncode, result.stderr)
            return None
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        _log.warning("hyprctl %s timed out", args)
    except json.JSONDecodeError as exc:
        _log.warning("hyprctl JSON parse error: %s", exc)
    except FileNotFoundError:
        _log.warning("hyprctl not found — is Hyprland running?")
    except Exception as exc:
        _log.warning("hyprctl error: %s", exc)
    return None


class WorkspaceMemory:
    """
    Track and restore which applications are open in each Hyprland workspace.

    Example
    -------
    >>> mem = WorkspaceMemory()
    >>> snap = mem.snapshot()   # {1: ["Firefox", "Alacritty"], 2: []}
    >>> mem.restore(snap)
    """

    def snapshot(self) -> dict[int, list[str]]:
        """
        Return a dict mapping workspace ID -> list of app names currently open.

        Returns an empty dict if hyprctl is unavailable (e.g. not on Hyprland).
        """
        data = _run_hyprctl(["clients", "-j"])
        if data is None:
            return {}

        # hyprctl clients -j returns a list directly
        clients = data if isinstance(data, list) else data.get("clients", [])

        workspace_apps: dict[int, list[str]] = {}
        for client in clients:
            workspace_id = client.get("workspace", {}).get("id", 0)
            if workspace_id == 0:
                continue
            app_name = client.get("class", "") or client.get("title", "<unknown>")
            workspace_apps.setdefault(workspace_id, []).append(app_name)

        _log.debug("Workspace snapshot: %s", workspace_apps)
        return workspace_apps

    def restore(self, snapshot: dict[int, list[str]]) -> None:
        """
        Restore windows to their original workspaces.

        Note: hyprctl cannot programmatically move windows between workspaces
        in a single call, so this method logs the intended state.
        The user can manually restore via the Hyprland UI.
        """
        current = self.snapshot()
        for workspace_id, app_names in snapshot.items():
            missing = [a for a in app_names if a not in current.get(workspace_id, [])]
            if missing:
                _log.info(
                    "Workspace %d missing apps (restore manually): %s",
                    workspace_id,
                    missing,
                )

    def save_snapshot(self, path: Optional[Path] = None) -> Path:
        """
        Save the current workspace snapshot to a JSON file.

        Returns the path where it was saved.
        """
        dest = path or SNAPSHOT_FILE
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(self.snapshot(), indent=2))
        _log.info("Workspace snapshot saved to %s", dest)
        return dest

    def load_snapshot(self, path: Optional[Path] = None) -> dict[int, list[str]]:
        """
        Load a workspace snapshot from a JSON file.

        Returns an empty dict if the file does not exist.
        Note: JSON keys are strings; they are converted back to int.
        """
        src = path or SNAPSHOT_FILE
        if not src.exists():
            _log.warning("No snapshot file at %s", src)
            return {}
        try:
            raw = json.loads(src.read_text())
            # JSON keys are strings; convert back to int
            return {int(k): v for k, v in raw.items()}
        except Exception as exc:
            _log.error("Failed to load snapshot from %s: %s", src, exc)
            return {}

    def saved_snapshot_exists(self, path: Optional[Path] = None) -> bool:
        """Return True if a saved snapshot file exists."""
        return (path or SNAPSHOT_FILE).exists()