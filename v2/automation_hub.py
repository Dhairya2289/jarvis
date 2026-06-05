"""
Local OS automation helpers for JARVIS.

These functions are intentionally small wrappers around common Linux desktop
commands. Tool dispatch in ``tools.py`` is responsible for exposing them to
the agent with typed schemas.
"""
from __future__ import annotations

import logging
import os
import shlex
import subprocess
from pathlib import Path

_log = logging.getLogger(__name__)


def _run(cmd: list[str], *, timeout: int = 20) -> str:
    """Run a sub-process and return its output or an error string."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        output = (result.stdout + result.stderr).strip()
        if result.returncode != 0:
            return f"[ERROR] {' '.join(cmd)} failed: {output}"
        return output or f"[OK] {' '.join(cmd)}"
    except FileNotFoundError:
        return f"[ERROR] Missing command: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return f"[ERROR] Command timed out: {' '.join(cmd)}"
    except Exception as exc:
        _log.error("Command failed: %s", exc, exc_info=True)
        return f"[ERROR] {exc}"


def execute_hardware(action: str, value: str = "") -> str:
    """Control volume, brightness, Wi‑Fi, Bluetooth, lock, and suspend."""
    value = str(value or "")
    actions: dict[str, list[str]] = {
        "volume_up": ["pamixer", "-i", value or "5"],
        "volume_down": ["pamixer", "-d", value or "5"],
        "volume_set": ["pamixer", "--set-volume", value.replace("%", "")],
        "mute_toggle": ["pamixer", "-t"],
        "mic_mute_toggle": ["pamixer", "--default-source", "-t"],
        "brightness_up": ["brightnessctl", "set", f"+{value or '10'}%"],
        "brightness_down": ["brightnessctl", "set", f"{value or '10'}%-"],
        "brightness_set": ["brightnessctl", "set", f"{value.replace('%', '')}%"],
        "wifi_on": ["nmcli", "radio", "wifi", "on"],
        "wifi_off": ["nmcli", "radio", "wifi", "off"],
        "bluetooth_on": ["bluetoothctl", "power", "on"],
        "bluetooth_off": ["bluetoothctl", "power", "off"],
        "suspend": ["systemctl", "suspend"],
        "sleep": ["systemctl", "suspend"],
        "lock": ["hyprlock"],
    }
    cmd = actions.get(action)
    if not cmd:
        return f"[ERROR] Unknown hardware action: {action}"
    return _run(cmd)


def execute_window(action: str, target: str = "") -> str:
    """Control Hyprland windows and workspaces."""
    actions: dict[str, list[str]] = {
        "close_active": ["hyprctl", "dispatch", "killactive"],
        "toggle_float": ["hyprctl", "dispatch", "togglefloating"],
        "toggle_fullscreen": ["hyprctl", "dispatch", "fullscreen"],
        "workspace_next": ["hyprctl", "dispatch", "workspace", "m+1"],
        "workspace_prev": ["hyprctl", "dispatch", "workspace", "m-1"],
        "workspace_empty": ["hyprctl", "dispatch", "workspace", "empty"],
        "move_to_workspace": ["hyprctl", "dispatch", "movetoworkspace", str(target)],
        "focus_app": ["hyprctl", "dispatch", "focuswindow", str(target)],
    }
    cmd = actions.get(action)
    if not cmd:
        return f"[ERROR] Unknown window action: {action}"
    return _run(cmd)


def execute_open_file(path: str) -> str:
    """Open a local file/dir or URL with the default application."""
    target = os.path.expanduser(path)
    if not target.startswith(("http://", "https://")) and not Path(target).exists():
        return f"[ERROR] File not found: {path}"
    try:
        subprocess.Popen(
            ["xdg-open", target],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return f"[OK] Opened: {path}"
    except FileNotFoundError:
        return "[ERROR] Missing command: xdg-open"
    except Exception as exc:
        _log.error("Open file failed: %s", exc, exc_info=True)
        return f"[ERROR] Failed to open file: {exc}"


def execute_process(action: str, target: str = "") -> str:
    """Launch, kill, or inspect processes."""
    try:
        if action == "launch":
            argv = shlex.split(target)
            if not argv:
                return "[ERROR] launch target is empty"
            subprocess.Popen(
                argv,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return f"[OK] Launched: {target}"
        if action == "kill":
            return _run(["killall", target])
        if action == "list_heavy":
            result = subprocess.run(
                ["ps", "-eo", "pid,pcpu,pmem,comm", "--sort=-pcpu"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            return "\n".join(result.stdout.strip().splitlines()[:12])
        return f"[ERROR] Unknown process action: {action}"
    except FileNotFoundError as exc:
        return f"[ERROR] Missing command: {exc.filename}"
    except Exception as exc:
        _log.error("Process control failed: %s", exc, exc_info=True)
        return f"[ERROR] Process control failed: {exc}"


def execute_git(action: str, target: str = ".", message: str = "") -> str:
    """Run safe Git status/commit/push operations in a target repo."""
    cwd = Path(target).expanduser()
    if not cwd.exists():
        return f"[ERROR] Path not found: {target}"
    if action == "status":
        return _git_run(cwd, ["status", "--short"])
    if action == "commit":
        add = _git_run(cwd, ["add", "."])
        if add.startswith("[ERROR]"):
            return add
        return _git_run(cwd, ["commit", "-m", message or "Jarvis Auto-Commit"])
    if action == "push":
        return _git_run(cwd, ["push"])
    return f"[ERROR] Unknown git action: {action}"


def _git_run(cwd: Path, args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        output = (result.stdout + result.stderr).strip()
        if result.returncode != 0:
            return f"[ERROR] git {' '.join(args)} failed: {output}"
        return output or f"[OK] git {' '.join(args)}"
    except FileNotFoundError:
        return "[ERROR] Missing command: git"
    except Exception as exc:
        _log.error("Git failed: %s", exc, exc_info=True)
        return f"[ERROR] Git failed: {exc}"


def execute_package(action: str, target: str) -> str:
    """Search or install Arch packages via paru."""
    if action == "search":
        return _run(["paru", "-Ss", target], timeout=30)[:4000]
    if action == "install":
        return _run(["paru", "-S", "--noconfirm", target], timeout=300)
    return f"[ERROR] Unknown package action: {action}"


def execute_resource_report() -> str:
    """Return a compact system health report."""
    try:
        import psutil

        lines = [
            f"CPU: {psutil.cpu_percent(interval=0.3)}%",
            f"RAM: {psutil.virtual_memory().percent}%",
            f"Disk: {psutil.disk_usage('/').percent}%",
        ]
        try:
            lines.append(_run(["uptime", "-p"]))
        except Exception:
            pass
        return "\n".join(lines)
    except Exception as exc:
        _log.error("Resource report failed: %s", exc, exc_info=True)
        return f"[ERROR] Resource report failed: {exc}"


def execute_media(action: str) -> str:
    """Control MPRIS media players through playerctl."""
    allowed = {"play", "pause", "play-pause", "next", "previous", "stop"}
    if action not in allowed:
        return f"[ERROR] Unknown media action: {action}"
    return _run(["playerctl", action])


__all__ = [
    "execute_hardware",
    "execute_window",
    "execute_open_file",
    "execute_process",
    "execute_git",
    "execute_package",
    "execute_resource_report",
    "execute_media",
]
