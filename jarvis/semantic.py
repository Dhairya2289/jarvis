"""JARVIS Semantic Scan — Desktop Window Layout"""
from __future__ import annotations

import json
import logging
import subprocess

_log = logging.getLogger(__name__)


def execute_semantic_scan() -> str:
    """Query Hyprland for current monitor and window state and return JSON."""
    try:
        try:
            clients_raw = subprocess.run(
                ["hyprctl", "clients", "-j"],
                capture_output=True,
                text=True,
                timeout=15,
            ).stdout
        except subprocess.TimeoutExpired:
            _log.warning("hyprctl clients timed out after 15s")
            return "[SEMANTIC ERROR] hyprctl clients timed out"
        try:
            monitors_raw = subprocess.run(
                ["hyprctl", "monitors", "-j"],
                capture_output=True,
                text=True,
                timeout=15,
            ).stdout
        except subprocess.TimeoutExpired:
            _log.warning("hyprctl monitors timed out after 15s")
            return "[SEMANTIC ERROR] hyprctl monitors timed out"

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
