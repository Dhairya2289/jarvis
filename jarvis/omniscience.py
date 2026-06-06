"""JARVIS Omniscience — Deep OS State Reader"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)


def read_os_mind() -> str:
    """Return a multi-section string summarising the current OS state."""
    sections: list[str] = []

    _append(sections, _active_window())
    _append(sections, _workspaces())
    _append(sections, _top_processes())
    _append(sections, _memory())
    _append(sections, _shell_history())
    _append(sections, _journal_errors())
    _append(sections, _disk_usage())

    return "\n".join(f"[{s}]" for s in sections) if sections else "[OS_MIND] No data."


def _append(sections: list[str], maybe: str | None) -> None:
    if maybe:
        sections.append(maybe)


def _active_window() -> str | None:
    try:
        raw = subprocess.run(
            ["hyprctl", "activewindow", "-j"],
            capture_output=True,
            text=True,
            timeout=15,
        ).stdout
    except subprocess.TimeoutExpired:
        _log.warning("hyprctl activewindow timed out after 15s")
        return None
        aw = json.loads(raw)
        return f"ACTIVE WINDOW: {aw.get('class', '?')} — {aw.get('title', '?')}"
    except Exception:
        return None


def _workspaces() -> str | None:
    try:
        raw = subprocess.run(
            ["hyprctl", "workspaces", "-j"],
            capture_output=True,
            text=True,
            timeout=15,
        ).stdout
    except subprocess.TimeoutExpired:
        _log.warning("hyprctl workspaces timed out after 15s")
        return None
        ws = json.loads(raw)
        occupied = [
            f"WS{w['id']}({w['windows']}wins)"
            for w in ws
            if w.get("windows", 0) > 0
        ]
        return f"WORKSPACES: {', '.join(occupied) or 'none'}"
    except Exception:
        return None


def _top_processes() -> str | None:
    try:
        r = subprocess.run(
            ["ps", "aux", "--sort=-%cpu", "--no-header"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        procs = [line.split()[10] for line in r.stdout.splitlines()[:5]]
        return f"TOP PROCESSES: {', '.join(procs)}"
    except Exception:
        return None


def _memory() -> str | None:
    try:
        r = subprocess.run(["free", "-h"], capture_output=True, text=True, timeout=15)
        for line in r.stdout.splitlines():
            if line.startswith("Mem:"):
                parts = line.split()
                return f"MEMORY: {parts[2]} used / {parts[1]} total"
    except Exception:
        return None
    return None


def _shell_history() -> str | None:
    for hist_file in [
        Path.home() / ".zsh_history",
        Path.home() / ".bash_history",
        Path.home() / ".local/share/fish/fish_history",
    ]:
        if not hist_file.exists():
            continue
        try:
            lines = hist_file.read_text(errors="ignore").splitlines()
            recent = [
                line.strip().lstrip(";0123456789: ")
                for line in lines[-10:]
                if line.strip()
            ]
            return "RECENT COMMANDS:\n  " + "\n  ".join(recent[-8:])
        except Exception:
            continue
    return None


def _journal_errors() -> str | None:
    try:
        r = subprocess.run(
            [
                "journalctl", "--user", "-p", "err", "-n", "5",
                "--no-pager", "--output", "short",
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if r.stdout.strip():
            return f"RECENT ERRORS:\n{r.stdout.strip()[:500]}"
    except Exception:
        return None
    return None


def _disk_usage() -> str | None:
    try:
        r = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=15)
        lines = r.stdout.splitlines()
        line = lines[-1] if lines else ""
        if line:
            parts = line.split()
            return f"DISK: {parts[2]} used / {parts[1]} ({parts[4]})"
    except Exception:
        return None
    return None


__all__ = ["read_os_mind"]
