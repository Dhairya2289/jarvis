"""JARVIS Semantic Scan — Desktop Window Layout"""
from __future__ import annotations

import json
import logging
import subprocess

_log = logging.getLogger(__name__)


def execute_semantic_scan() -> str:
    """Query Hyprland for current monitor and window state and return JSON."""
    try:
        clients_raw = subprocess.run(
            ["hyprctl", "clients", "-j"],
            capture_output=True,
            text=True,
        ).stdout
        monitors_raw = subprocess.run(
            ["hyprctl", "monitors", "-j"],
            capture_output=True,
            text=True,
        ).stdout

        clients = json.loads(clients_raw)
        monitors = json.loads(monitors_raw)

        result = {
            "monitors": [
                {
                    "id": m["id"],
                    "res": f"{m['width']}x{m['height']}",
                    "scale": m.get("scale", 1),
                }
                for m in monitors
            ],
            "windows": [
                {
                    "ws": c["workspace"]["id"],
                    "class": c["class"],
                    "title": c["title"][:60],
                    "at": c["at"],
                    "size": c["size"],
                    "focused": c.get("focused", False),
                }
                for c in clients
            ],
        }
        return json.dumps(result, indent=2)
    except Exception as exc:
        _log.error("Semantic scan failed: %s", exc, exc_info=True)
        return f"[SEMANTIC ERROR] {exc}"


__all__ = ["execute_semantic_scan"]
