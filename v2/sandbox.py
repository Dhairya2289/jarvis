"""JARVIS Sandbox — Isolated Execution Environment"""
from __future__ import annotations

import logging
import shutil
import subprocess
import time
from pathlib import Path
from typing import Final

from config import BLOCKED_COMMANDS, SANDBOX_DIR

_log = logging.getLogger(__name__)

_ESCAPE_PATTERNS: Final[list[str]] = [
    "cd /",
    "cd ~",
    "../..",
    "HOME=",
    "PATH=",
]


def _is_safe(command: str) -> tuple[bool, str]:
    """Return (ok, reason) after checking *command* against block lists."""
    for blocked in BLOCKED_COMMANDS:
        if blocked in command:
            return False, f"dangerous: {blocked}"
    for pattern in _ESCAPE_PATTERNS:
        if pattern in command:
            return False, f"escape attempt: {pattern}"
    return True, ""


def execute_sandboxed_bash(
    command: str, *, timeout: int = 60
) -> str:
    """Run *command* inside SANDBOX_DIR and return output / error text."""
    safe, reason = _is_safe(command)
    if not safe:
        return f"[SANDBOX BLOCKED] {reason}"

    SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
    wrapped = f"cd {SANDBOX_DIR} && {command}"
    try:
        start = time.time()
        result = subprocess.run(
            wrapped,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            executable="/bin/bash",
            cwd=str(SANDBOX_DIR),
        )
        elapsed = round(time.time() - start, 2)
        status = "SUCCESS" if result.returncode == 0 else "ERROR"
        return (
            f"[SANDBOX {status} | exit={result.returncode} | {elapsed}s]\n"
            f"{(result.stdout + result.stderr)[:5000]}"
        )
    except subprocess.TimeoutExpired:
        return "[SANDBOX TIMEOUT] Command exceeded limit."
    except Exception as exc:
        _log.error("Sandbox execution failed: %s", exc, exc_info=True)
        return f"[SANDBOX SYSTEM ERROR] {exc}"


def deploy_to_production(filename: str, target_path: str) -> str:
    """Copy *filename* from SANDBOX_DIR to *target_path*."""
    src = SANDBOX_DIR / filename
    dest = Path(target_path).expanduser()
    if not src.exists():
        return f"[DEPLOY ERROR] Source not found: {filename}"
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return f"[DEPLOYED] {filename} → {dest}"
    except Exception as exc:
        _log.error("Deploy failed: %s", exc, exc_info=True)
        return f"[DEPLOY ERROR] {exc}"


def clear_sandbox() -> str:
    """Remove all contents of SANDBOX_DIR."""
    try:
        for item in SANDBOX_DIR.iterdir():
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)
        return "[SANDBOX] Cleared."
    except Exception as exc:
        _log.error("Clear sandbox failed: %s", exc, exc_info=True)
        return f"[ERROR] {exc}"


__all__ = ["execute_sandboxed_bash", "deploy_to_production", "clear_sandbox"]
