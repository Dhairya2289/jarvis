"""
JARVIS V3 — Tool Registry + Dispatchers
──────────────────────────────────────────────────────────────
All tools the agent can call.
  • JSON schemas for LLM tool use
  • Central dispatch with _DISPATCH_EXTRA hook
  • Linux / Hyprland native controls
"""

import os
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List

from jarvis_v3.config import BLOCKED_COMMANDS

# ── Runtime hook for self-evolved / external tools ────────
_DISPATCH_EXTRA: Dict[str, Callable] = {}


def register_tool(name: str, fn: Callable) -> None:
    """Register an external tool at runtime."""
    _DISPATCH_EXTRA[name] = fn


# ── Tool Schemas ──────────────────────────────────────────

TOOL_DEFINITIONS: List[dict] = [
    {
        "name": "desktop_notification",
        "description": "Show a desktop HUD notification.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "message": {"type": "string"},
                "urgency": {"type": "string", "enum": ["low", "normal", "critical"], "default": "normal"},
            },
            "required": ["title", "message"],
        },
    },
    {
        "name": "os_hardware_control",
        "description": "Control volume, brightness, Wi-Fi, Bluetooth, lock, or suspend.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "volume_up", "volume_down", "volume_set", "mute_toggle",
                        "brightness_up", "brightness_down", "brightness_set",
                        "wifi_on", "wifi_off", "bluetooth_on", "bluetooth_off",
                        "suspend", "sleep", "lock",
                    ],
                },
                "value": {"type": "string", "default": ""},
            },
            "required": ["action"],
        },
    },
    {
        "name": "os_process_control",
        "description": "Launch or kill a process.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["launch", "kill"]},
                "target": {"type": "string"},
            },
            "required": ["action", "target"],
        },
    },
    {
        "name": "bash",
        "description": "Execute a bash command with safety checks.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "find_and_open_file",
        "description": "Find a file by name under the home directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string"},
                "open": {"type": "boolean", "default": True},
            },
            "required": ["filename"],
        },
    },
    {
        "name": "read_file",
        "description": "Read contents of a file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "limit": {"type": "integer", "default": 500},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write text to a file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "mode": {"type": "string", "enum": ["write", "append"], "default": "write"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "git_ops",
        "description": "Run git commands in the current or specified directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "cwd": {"type": "string", "default": "."},
            },
            "required": ["command"],
        },
    },
    {
        "name": "system_health_report",
        "description": "Get CPU, RAM, disk, and temperature info.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "take_screenshot",
        "description": "Capture a screenshot and return the file path.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "speak",
        "description": "Speak a message using TTS.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "spawn_agent",
        "description": "Spawn a specialist sub-agent for a sub-task.",
        "input_schema": {
            "type": "object",
            "properties": {
                "specialist": {"type": "string"},
                "task": {"type": "string"},
            },
            "required": ["specialist", "task"],
        },
    },
    {
        "name": "browser_interact",
        "description": "Use browser-use to perform a web task (navigate, search, extract content).",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Natural-language instruction for the browser agent."},
                "model": {"type": "string", "default": "gpt-4o"},
                "headless": {"type": "boolean", "default": True},
            },
            "required": ["task"],
        },
    },
    {
        "name": "ocr_extract",
        "description": "Extract text from an image using PaddleOCR.",
        "input_schema": {
            "type": "object",
            "properties": {
                "image_path": {"type": "string", "description": "Path to the image file."},
            },
            "required": ["image_path"],
        },
    },
    {
        "name": "optimize_prompt",
        "description": "Iteratively optimize a prompt for a given task using LLM critique.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Task description."},
                "initial_prompt": {"type": "string", "description": "Starting prompt."},
                "iterations": {"type": "integer", "default": 3},
            },
            "required": ["task", "initial_prompt"],
        },
    },
    {
        "name": "cron_add",
        "description": "Schedule a recurring task. Examples: 'every 30 minutes', 'daily at 9am', 'weekly on mon at 10:00'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Human-readable job name."},
                "schedule": {"type": "string", "description": "Natural-language schedule."},
                "prompt": {"type": "string", "description": "Task text for the agent."},
            },
            "required": ["name", "schedule", "prompt"],
        },
    },
    {
        "name": "cron_list",
        "description": "List all scheduled cron jobs.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "cron_remove",
        "description": "Remove a cron job by ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
            },
            "required": ["job_id"],
        },
    },
    {
        "name": "dream_consolidate",
        "description": "Trigger background memory consolidation (AutoDream).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "compress_context",
        "description": "Compress long conversation history using LLM summarisation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session to compress."},
            },
            "required": ["session_id"],
        },
    },
]


# ── Dispatch ──────────────────────────────────────────────


def dispatch_tool(name: str, args: Dict[str, Any]) -> str:
    """Route a tool call to its implementation."""
    if name in _DISPATCH_EXTRA:
        try:
            return str(_DISPATCH_EXTRA[name](**args))
        except Exception as e:
            return f"[ERROR] {e}"

    fn = _DISPATCH_MAP.get(name)
    if not fn:
        return f"[ERROR] Unknown tool: {name}"
    try:
        return str(fn(**args))
    except Exception as e:
        return f"[ERROR] {e}"


# ── Implementations ───────────────────────────────────────


def _desktop_notification(title: str, message: str, urgency: str = "normal") -> str:
    subprocess.run(
        ["notify-send", f"--urgency={urgency}", title, message],
        capture_output=True,
    )
    return f"Notification sent: {title}"


def _os_hardware_control(action: str, value: str = "") -> str:
    cmds = {
        "volume_up": ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+5%"],
        "volume_down": ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-5%"],
        "mute_toggle": ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"],
        "brightness_up": ["brightnessctl", "set", "+5%"],
        "brightness_down": ["brightnessctl", "set", "5%-"],
        "wifi_on": ["nmcli", "radio", "wifi", "on"],
        "wifi_off": ["nmcli", "radio", "wifi", "off"],
        "bluetooth_on": ["bluetoothctl", "power", "on"],
        "bluetooth_off": ["bluetoothctl", "power", "off"],
        "lock": ["hyprlock"],
        "suspend": ["systemctl", "suspend"],
        "sleep": ["systemctl", "suspend"],
    }
    if action == "volume_set" and value:
        cmd = ["pactl", "set-sink-volume", "@DEFAULT_SINK@", value]
    elif action == "brightness_set" and value:
        cmd = ["brightnessctl", "set", value]
    else:
        cmd = cmds.get(action)
    if not cmd:
        return f"[ERROR] Unknown hardware action: {action}"
    subprocess.run(cmd, capture_output=True)
    return f"Executed: {action}"


def _os_process_control(action: str, target: str) -> str:
    if action == "launch":
        subprocess.Popen(target, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"Launched: {target}"
    elif action == "kill":
        subprocess.run(["killall", target], capture_output=True)
        return f"Killed: {target}"
    return f"[ERROR] Unknown action: {action}"


def _bash(command: str) -> str:
    for blocked in BLOCKED_COMMANDS:
        if blocked in command:
            return f"[BLOCKED] Command contains forbidden pattern: {blocked}"
    try:
        r = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
        out = r.stdout.strip() or r.stderr.strip() or "(no output)"
        return out[:4000]
    except subprocess.TimeoutExpired:
        return "[TIMEOUT] Command exceeded 30s"
    except Exception as e:
        return f"[ERROR] {e}"


def _find_and_open_file(filename: str, open_file: bool = True) -> str:
    home = Path.home()
    matches = list(home.rglob(f"*{filename}*"))
    if not matches:
        return f"[ERROR] No file matching '{filename}' found."
    best = matches[0]
    if open_file:
        subprocess.run(["xdg-open", str(best)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return str(best)


def _read_file(path: str, limit: int = 500) -> str:
    try:
        return Path(path).read_text()[:limit]
    except Exception as e:
        return f"[ERROR] {e}"


def _write_file(path: str, content: str, mode: str = "write") -> str:
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        if mode == "append":
            p.write_text(p.read_text() + content)
        else:
            p.write_text(content)
        return f"Wrote {len(content)} chars to {path}"
    except Exception as e:
        return f"[ERROR] {e}"


def _git_ops(command: str, cwd: str = ".") -> str:
    try:
        r = subprocess.run(
            ["git"] + command.split(),
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        out = r.stdout.strip() or r.stderr.strip() or "(no output)"
        return out[:4000]
    except Exception as e:
        return f"[ERROR] {e}"


def _system_health_report() -> str:
    try:
        cpu = subprocess.run(["cat", "/proc/loadavg"], capture_output=True, text=True).stdout.split()[0]
        mem = subprocess.run(["free", "-h"], capture_output=True, text=True).stdout.split("\n")[1]
        disk = subprocess.run(["df", "-h", "/"], capture_output=True, text=True).stdout.split("\n")[1]
        return f"CPU load: {cpu}\nMemory: {mem}\nDisk: {disk}"
    except Exception as e:
        return f"[ERROR] {e}"


def _take_screenshot() -> str:
    path = Path.home() / ".jarvis" / "screenshot.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Try grim first (Wayland)
        subprocess.run(["grim", str(path)], capture_output=True, timeout=5)
        if path.exists():
            return str(path)
    except Exception:
        pass
    try:
        # Fallback to mss / PIL
        import mss
        with mss.mss() as sct:
            sct.shot(output=str(path))
        return str(path)
    except Exception:
        pass
    return "[ERROR] Screenshot failed"


def _speak(text: str) -> str:
    try:
        subprocess.run(["espeak-ng", text], capture_output=True, timeout=10)
    except Exception:
        try:
            subprocess.run(["espeak", text], capture_output=True, timeout=10)
        except Exception:
            return f"[ERROR] TTS failed for: {text}"
    return f"Spoke: {text[:60]}..."


def _spawn_agent(specialist: str, task: str) -> str:
    """Spawn a specialist sub-agent with a loaded prompt template."""
    try:
        from jarvis_v3.specialists import load_specialist, list_specialists
        if specialist in list_specialists():
            prompt = load_specialist(specialist)
            return f"[{specialist.upper()} MODE ACTIVATED]\n{prompt}\n\nTask: {task}"
    except Exception:
        pass
    return f"[DELEGATED to {specialist}] {task}"


def _browser_interact(task: str, model: str = "gpt-4o", headless: bool = True) -> str:
    """Delegate to browser-use plugin."""
    try:
        from jarvis_v3.plugins.browser_use_plugin import run_sync
        return run_sync(task, model=model, headless=headless)
    except Exception as exc:
        return f"[BROWSER ERROR] {exc}"


def _ocr_extract(image_path: str) -> str:
    """Delegate to PaddleOCR plugin."""
    try:
        from jarvis_v3.plugins.paddleocr_plugin import extract_text
        return extract_text(image_path)
    except Exception as exc:
        return f"[OCR ERROR] {exc}"


def _optimize_prompt(task: str, initial_prompt: str, iterations: int = 3) -> str:
    """Delegate to prompt-optimizer plugin."""
    try:
        from jarvis_v3.plugins.prompt_optimizer_plugin import optimize
        result = optimize(task, initial_prompt, iterations=iterations)
        return result["best_prompt"]
    except Exception as exc:
        return f"[PROMPT OPT ERROR] {exc}"


def _cron_add(name: str, schedule: str, prompt: str) -> str:
    try:
        from jarvis_v3.cron_scheduler import add_job
        return add_job(name, schedule, prompt)
    except Exception as exc:
        return f"[CRON ERROR] {exc}"


def _cron_list() -> str:
    try:
        from jarvis_v3.cron_scheduler import list_jobs
        return list_jobs()
    except Exception as exc:
        return f"[CRON ERROR] {exc}"


def _cron_remove(job_id: str) -> str:
    try:
        from jarvis_v3.cron_scheduler import remove_job
        return remove_job(job_id)
    except Exception as exc:
        return f"[CRON ERROR] {exc}"


def _dream_consolidate() -> str:
    try:
        from jarvis_v3.auto_dream import tick
        return tick()
    except Exception as exc:
        return f"[DREAM ERROR] {exc}"


def _compress_context(session_id: str) -> str:
    """Compress the session's conversation history."""
    try:
        from jarvis_v3.session_memory import get_session_context
        from jarvis_v3.context_compressor import compress
        msgs = get_session_context(session_id)
        compressed = compress(msgs)
        return f"Compressed {len(msgs)} → {len(compressed)} turns"
    except Exception as exc:
        return f"[COMPRESS ERROR] {exc}"


_DISPATCH_MAP = {
    "desktop_notification": _desktop_notification,
    "os_hardware_control": _os_hardware_control,
    "os_process_control": _os_process_control,
    "bash": _bash,
    "find_and_open_file": _find_and_open_file,
    "read_file": _read_file,
    "write_file": _write_file,
    "git_ops": _git_ops,
    "system_health_report": _system_health_report,
    "take_screenshot": _take_screenshot,
    "speak": _speak,
    "spawn_agent": _spawn_agent,
    "browser_interact": _browser_interact,
    "ocr_extract": _ocr_extract,
    "optimize_prompt": _optimize_prompt,
    "cron_add": _cron_add,
    "cron_list": _cron_list,
    "cron_remove": _cron_remove,
    "dream_consolidate": _dream_consolidate,
    "compress_context": _compress_context,
}
