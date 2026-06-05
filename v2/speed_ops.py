"""Fast local operations for Jarvis."""
from __future__ import annotations

import logging
import subprocess

_log = logging.getLogger(__name__)


def execute_lightning_play(query: str) -> str:
    """Play audio quickly using mpv's yt-dlp integration."""
    try:
        subprocess.Popen(
            [
                "mpv", "--no-video", "--ytdl-format=bestaudio",
                f"ytdl://ytsearch1:{query}",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return f"[OK] Lightning audio started for: {query}"
    except FileNotFoundError:
        return "[ERROR] mpv is not installed"
    except Exception as exc:
        _log.error("Lightning play failed: %s", exc, exc_info=True)
        return f"[ERROR] Lightning Play failed: {exc}"


def execute_high_speed_plan(commands: list[str]) -> str:
    """Run a short sequence of shell commands. Host safety checks happen in tools.py."""
    results: list[str] = []
    for command in commands:
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=20,
                executable="/bin/bash",
            )
            status = "SUCCESS" if result.returncode == 0 else "FAILED"
            output = (result.stdout + result.stderr).strip()
            results.append(f"{status}: {command}\n{output[:500]}")
        except Exception as exc:
            results.append(f"FAILED: {command} ({exc})")
    return "\n".join(results)


__all__ = ["execute_lightning_play", "execute_high_speed_plan"]
