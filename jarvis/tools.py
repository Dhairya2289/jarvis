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
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List

from jarvis.config import BLOCKED_COMMANDS

# ── Runtime hook for self-evolved / external tools ────────
_DISPATCH_EXTRA: Dict[str, Callable] = {}


def register_tool(name: str, func: Callable):
    """Register a user skill or dynamically loaded tool."""
    _DISPATCH_EXTRA[name] = func


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
    {
        "name": "obsidian_create",
        "description": "Create a note in the JARVIS Obsidian brain.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "content": {"type": "string"},
                "folder": {"type": "string", "default": "general"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["name", "content"],
        },
    },
    {
        "name": "obsidian_read",
        "description": "Read a note from the JARVIS Obsidian brain.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "folder": {"type": "string", "default": "general"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "obsidian_search",
        "description": "Search notes in the JARVIS Obsidian brain.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "folder": {"type": "string"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "obsidian_daily",
        "description": "Get or create today's daily note in Obsidian.",
        "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}},
    },
    {
        "name": "skill_run",
        "description": "Run a dynamically discovered skill by name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "args": {"type": "object"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "skill_list",
        "description": "List all available skills.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "memdir_add",
        "description": "Add a memory entry to the typed memory directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "mem_type": {"type": "string", "enum": ["fact", "preference", "error", "task", "insight"]},
                "confidence": {"type": "number", "default": 0.8},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["content", "mem_type"],
        },
    },
    {
        "name": "memdir_search",
        "description": "Search the typed memory directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "mem_type": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "list_apps",
        "description": "List all installed desktop applications.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "search_apps",
        "description": "Search installed apps by name, category, or keyword.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "launch_app",
        "description": "Launch a desktop application by its display name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "focus_app",
        "description": "Focus an existing application window via Hyprland.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "mcp_start",
        "description": "Start the JARVIS MCP server so your phone can connect.",
        "input_schema": {
            "type": "object",
            "properties": {
                "port": {"type": "integer", "default": 8765},
            },
        },
    },
    {
        "name": "mcp_status",
        "description": "Get the MCP server URL and status for phone pairing.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "proactive_start",
        "description": "Start the proactive agent loop (system monitor daemon).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "proactive_stop",
        "description": "Stop the proactive agent loop.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "autoskill_review",
        "description": "Review detected tool-usage patterns and auto-skills.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "autoskill_prune",
        "description": "Clean old tool-usage patterns from auto-skill detector.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "markitdown_convert",
        "description": "Convert any document (PDF, PPTX, DOCX, XLSX) to markdown using markitdown.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file to convert."},
                "save_to_obsidian": {"type": "boolean", "default": True},
            },
            "required": ["path"],
        },
    },
    {
        "name": "file_search",
        "description": "Search files by name/content using a SQLite FTS5 index.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
            },
            "required": ["query"],
        },
    },
    {
        "name": "universal_search",
        "description": "Search across files, desktop apps, and Obsidian vault simultaneously.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "scopes": {"type": "array", "items": {"type": "string"}, "default": ["files", "apps", "vault"]},
            },
            "required": ["query"],
        },
    },
    {
        "name": "ingest_pdf",
        "description": "Extract text from a PDF and save it as an Obsidian markdown note.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pdf_path": {"type": "string"},
            },
            "required": ["pdf_path"],
        },
    },
    {
        "name": "organize_downloads",
        "description": "Auto-sort files in ~/Downloads into category folders by MIME type. Pass dry_run=True to preview without moving.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dry_run": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "name": "fetch_rss_digest",
        "description": "Fetch all configured RSS feeds and return new entries as a markdown digest.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "add_todo",
        "description": "Parse a natural-language message into to-do items and append them to the Obsidian Inbox.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
            },
            "required": ["message"],
        },
    },
    {
        "name": "list_todos",
        "description": "List to-do items from the Obsidian Inbox, optionally filtered by status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["open", "done", "all"], "default": "open"},
            },
        },
    },
    {
        "name": "snapshot_workspace",
        "description": "Snapshot current Hyprland workspace layout (which apps are open in each workspace).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "restore_workspace",
        "description": "Restore a Hyprland workspace snapshot previously created with snapshot_workspace.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "launch_best",
        "description": "Smart launcher: resolve and open the best match for a query across apps, files, and Obsidian vault.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "recent_clipboard",
        "description": "Return the n most recent clipboard entries (newest first).",
        "input_schema": {
            "type": "object",
            "properties": {
                "n": {"type": "integer", "default": 20},
            },
        },
    },
    {
        "name": "recent_notifications",
        "description": "Return the n most recent desktop notifications, grouped by app.",
        "input_schema": {
            "type": "object",
            "properties": {
                "n": {"type": "integer", "default": 10},
            },
        },
    },
    {
        "name": "archive_screenshots",
        "description": "Organise screenshots into date folders and archive files older than 30 days.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "window_timeline",
        "description": "Return recent active window focus events as a timeline.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hours": {"type": "integer", "default": 1},
            },
        },
    },
    {
        "name": "screen_pointer",
        "description": "Find and click a UI element described in natural language.",
        "input_schema": {
            "type": "object",
            "properties": {
                "element": {"type": "string", "description": "What to click, e.g. 'the Save button'"},
            },
            "required": ["element"],
        },
    },
    {
        "name": "screen_explain",
        "description": "Drag-select a screen region and get an AI explanation of what's shown.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
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
    try:
        subprocess.run(
            ["notify-send", f"--urgency={urgency}", title, message],
            capture_output=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        pass
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
    try:
        subprocess.run(cmd, capture_output=True, timeout=15)
    except subprocess.TimeoutExpired:
        return f"[ERROR] Hardware command timed out after 15s: {action}"
    return f"Executed: {action}"


def _os_process_control(action: str, target: str) -> str:
    if action == "launch":
        subprocess.Popen(target, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"Launched: {target}"
    elif action == "kill":
        try:
            subprocess.run(["killall", target], capture_output=True, timeout=15)
        except subprocess.TimeoutExpired:
            return f"[ERROR] killall timed out for: {target}"
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
        try:
            subprocess.run(["xdg-open", str(best)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        except subprocess.TimeoutExpired:
            return f"[ERROR] xdg-open timed out for: {best}"
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
        cpu = subprocess.run(["cat", "/proc/loadavg"], capture_output=True, text=True, timeout=15).stdout.split()[0]
        mem = subprocess.run(["free", "-h"], capture_output=True, text=True, timeout=15).stdout.split("\n")[1]
        disk = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=15).stdout.split("\n")[1]
        return f"CPU load: {cpu}\nMemory: {mem}\nDisk: {disk}"
    except subprocess.TimeoutExpired:
        return "[ERROR] System health check timed out after 15s"
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
        from jarvis.specialists import load_specialist, list_specialists
        if specialist in list_specialists():
            prompt = load_specialist(specialist)
            return f"[{specialist.upper()} MODE ACTIVATED]\n{prompt}\n\nTask: {task}"
    except Exception:
        pass
    return f"[DELEGATED to {specialist}] {task}"


def _browser_interact(task: str, model: str = "gpt-4o", headless: bool = True) -> str:
    """Delegate to browser-use plugin."""
    try:
        from jarvis.plugins.browser_use_plugin import run_sync
        return run_sync(task, model=model, headless=headless)
    except Exception as exc:
        return f"[BROWSER ERROR] {exc}"


def _ocr_extract(image_path: str) -> str:
    """Delegate to PaddleOCR plugin."""
    try:
        from jarvis.plugins.paddleocr_plugin import extract_text
        return extract_text(image_path)
    except Exception as exc:
        return f"[OCR ERROR] {exc}"


def _optimize_prompt(task: str, initial_prompt: str, iterations: int = 3) -> str:
    """Delegate to prompt-optimizer plugin."""
    try:
        from jarvis.plugins.prompt_optimizer_plugin import optimize
        result = optimize(task, initial_prompt, iterations=iterations)
        return result["best_prompt"]
    except Exception as exc:
        return f"[PROMPT OPT ERROR] {exc}"


def _cron_add(name: str, schedule: str, prompt: str) -> str:
    try:
        from jarvis.cron_scheduler import add_job
        return add_job(name, schedule, prompt)
    except Exception as exc:
        return f"[CRON ERROR] {exc}"


def _cron_list() -> str:
    try:
        from jarvis.cron_scheduler import list_jobs
        return list_jobs()
    except Exception as exc:
        return f"[CRON ERROR] {exc}"


def _cron_remove(job_id: str) -> str:
    try:
        from jarvis.cron_scheduler import remove_job
        return remove_job(job_id)
    except Exception as exc:
        return f"[CRON ERROR] {exc}"


def _dream_consolidate() -> str:
    try:
        from jarvis.auto_dream import tick
        return tick()
    except Exception as exc:
        return f"[DREAM ERROR] {exc}"


def _compress_context(session_id: str) -> str:
    """Compress the session's conversation history."""
    try:
        from jarvis.session_memory import get_session_context
        from jarvis.context_compressor import compress
        msgs = get_session_context(session_id)
        compressed = compress(msgs)
        return f"Compressed {len(msgs)} → {len(compressed)} turns"
    except Exception as exc:
        return f"[COMPRESS ERROR] {exc}"


def _obsidian_create(name: str, content: str, folder: str = "general", tags: list | None = None) -> str:
    try:
        from jarvis.obsidian_brain import ObsidianBrain
        path = ObsidianBrain().create_note(name, content, folder=folder, tags=tags or [])
        return f"[OBSIDIAN] Created: {path}"
    except Exception as exc:
        return f"[OBSIDIAN ERROR] {exc}"


def _obsidian_read(name: str, folder: str = "general") -> str:
    try:
        from jarvis.obsidian_brain import ObsidianBrain
        note = ObsidianBrain().read_note(name, folder=folder)
        return note["content"]
    except Exception as exc:
        return f"[OBSIDIAN ERROR] {exc}"


def _obsidian_search(query: str, folder: str | None = None) -> str:
    try:
        from jarvis.obsidian_brain import ObsidianBrain
        results = ObsidianBrain().search(query, folder=folder)
        if not results:
            return "No notes found."
        return "\n".join(f"- {r['name']} ({r['folder']}): {r['content'][:100]}..." for r in results[:10])
    except Exception as exc:
        return f"[OBSIDIAN ERROR] {exc}"


def _obsidian_daily(text: str = "") -> str:
    try:
        from jarvis.obsidian_brain import ObsidianBrain
        brain = ObsidianBrain()
        path = brain.get_daily_note()
        if text:
            brain.append_daily(text)
        return f"[OBSIDIAN] Daily note: {path}"
    except Exception as exc:
        return f"[OBSIDIAN ERROR] {exc}"


def _skill_run(name: str, args: dict | None = None) -> str:
    try:
        from jarvis.skill_system import SkillRegistry
        registry = SkillRegistry()
        registry.discover()
        result = registry.run(name, **(args or {}))
        return str(result)
    except Exception as exc:
        return f"[SKILL ERROR] {exc}"


def _skill_list() -> str:
    try:
        from jarvis.skill_system import SkillRegistry
        registry = SkillRegistry()
        registry.discover()
        return registry.list_skills()
    except Exception as exc:
        return f"[SKILL ERROR] {exc}"


def _memdir_add(content: str, mem_type: str, confidence: float = 0.8, tags: list | None = None) -> str:
    try:
        from jarvis.memdir import MemDir
        mid = MemDir().add(content, mem_type, confidence=confidence, tags=tags or [])
        return f"[MEMDIR] Added: {mid}"
    except Exception as exc:
        return f"[MEMDIR ERROR] {exc}"


def _memdir_search(query: str, mem_type: str | None = None, limit: int = 10) -> str:
    try:
        from jarvis.memdir import MemDir
        results = MemDir().search(query, mem_type=mem_type, limit=limit)
        if not results:
            return "No memories found."
        return "\n".join(f"- [{r.mem_type}] {r.content[:80]}... (confidence={r.confidence:.2f})" for r in results)
    except Exception as exc:
        return f"[MEMDIR ERROR] {exc}"


def _list_apps() -> str:
    try:
        from jarvis.apps.desktop import list_apps
        apps = list_apps()
        return "\n".join(f"- {a.name}" for a in apps[:50])
    except Exception as exc:
        return f"[DESKTOP ERROR] {exc}"


def _search_apps(query: str) -> str:
    try:
        from jarvis.apps.desktop import search_apps
        results = search_apps(query)
        if not results:
            return f"No apps matching '{query}'."
        return "\n".join(f"- {a.name}: {a.exec}" for a in results[:20])
    except Exception as exc:
        return f"[DESKTOP ERROR] {exc}"


def _launch_app(name: str) -> str:
    try:
        from jarvis.apps.desktop import launch_app
        return launch_app(name)
    except Exception as exc:
        return f"[DESKTOP ERROR] {exc}"


def _focus_app(name: str) -> str:
    try:
        from jarvis.apps.desktop import focus_app
        return focus_app(name)
    except Exception as exc:
        return f"[DESKTOP ERROR] {exc}"


def _focus_mode(duration: int = 25) -> str:
    """Activate Pomodoro focus mode: close distractions, pause notifications."""
    try:
        import subprocess
        subprocess.run(["hyprctl", "dispatch", "closewindow", "class:discord"], capture_output=True, timeout=3)
        subprocess.run(["hyprctl", "dispatch", "closewindow", "class:telegram-desktop"], capture_output=True, timeout=3)
        subprocess.run(["dunstctl", "set-paused", "true"], capture_output=True, timeout=3)
        return f"🔴 Focus mode ON ({duration} min). Notifications paused, distractions closed."
    except Exception as exc:
        return f"[FOCUS ERROR] {exc}"


def _mcp_start(port: int = 8765) -> str:
    try:
        import threading
        from jarvis.mcp_server import start_server
        def _run():
            start_server(port=port)
        t = threading.Thread(target=_run, daemon=True)
        t.start()
        from jarvis.mcp_server import get_lan_ip
        return f"[MCP] Server starting on http://{get_lan_ip()}:{port}/sse in background thread."
    except Exception as exc:
        return f"[MCP ERROR] {exc}"


def _mcp_status() -> str:
    try:
        from jarvis.mcp_server import get_lan_ip
        url = f"http://{get_lan_ip()}:8765/sse"
        return f"[MCP] Server URL: {url}\nAdd this URL to Edge Gallery → MCP → Add Server"
    except Exception as exc:
        return f"[MCP ERROR] {exc}"


def _proactive_start() -> str:
    try:
        from jarvis.proactive_loop import ProactiveLoop
        loop = ProactiveLoop()
        loop.start()
        return "[PROACTIVE] Loop started (checks every 60s)"
    except Exception as exc:
        return f"[PROACTIVE ERROR] {exc}"


def _proactive_stop() -> str:
    try:
        from jarvis.proactive_loop import ProactiveLoop
        # Singleton-ish: create new and stop immediately
        loop = ProactiveLoop()
        loop.stop()
        return "[PROACTIVE] Loop stopped"
    except Exception as exc:
        return f"[PROACTIVE ERROR] {exc}"


def _autoskill_review() -> str:
    try:
        from jarvis.auto_skills import AutoSkillDetector
        return AutoSkillDetector().review()
    except Exception as exc:
        return f"[AUTOSKILL ERROR] {exc}"


def _autoskill_prune() -> str:
    try:
        from jarvis.auto_skills import AutoSkillDetector
        removed = AutoSkillDetector().prune()
        return f"[AUTOSKILL] Pruned {removed} old patterns"
    except Exception as exc:
        return f"[AUTOSKILL ERROR] {exc}"


def _markitdown_convert(path: str, save_to_obsidian: bool = True) -> str:
    try:
        from markitdown import MarkItDown
        from pathlib import Path
        result = MarkItDown().convert(path)
        text = result.text_content
        if save_to_obsidian:
            from jarvis.obsidian_brain import ObsidianBrain
            name = Path(path).stem
            ObsidianBrain().create_note(
                name=f"converted_{name}",
                content=text[:5000],
                folder="imports",
                tags=["markitdown", Path(path).suffix.lstrip(".")],
            )
        return f"[MARKITDOWN] Converted {path} ({len(text)} chars)"
    except Exception as exc:
        return f"[MARKITDOWN ERROR] {exc}"


def _file_search(query: str, limit: int = 20) -> str:
    try:
        from jarvis.file_search_index import FileSearchIndex
        return FileSearchIndex.search(query, limit=limit)
    except Exception as exc:
        return f"[ERROR] {exc}"


def _universal_search(query: str, scopes: list = ["files", "apps", "vault"]) -> str:
    try:
        from jarvis.universal_search import universal_search
        return universal_search(query, scopes=scopes)
    except Exception as exc:
        return f"[ERROR] {exc}"


def _ingest_pdf(pdf_path: str) -> str:
    try:
        from jarvis.pdf_ingestion import PDFIngestion
        return PDFIngestion().ingest(Path(pdf_path))
    except Exception as exc:
        return f"[ERROR] {exc}"


def _organize_downloads(dry_run: bool = False) -> str:
    try:
        from jarvis.download_organizer import DownloadOrganizer
        return DownloadOrganizer().organize(dry_run=dry_run)
    except Exception as exc:
        return f"[ERROR] {exc}"


def _fetch_rss_digest() -> str:
    try:
        from jarvis.rss_reader import RSSReader
        return RSSReader().get_digest(datetime.now() - timedelta(days=1))
    except Exception as exc:
        return f"[ERROR] {exc}"


def _add_todo(message: str) -> str:
    try:
        from jarvis.smart_todo import SmartTodo
        vault_path = Path.home() / "Documents" / "vault"
        todo = SmartTodo(vault_path)
        items = todo.parse_message(message)
        todo.add_items(*items)
        return f"[TODO] Added {len(items)} item(s)"
    except Exception as exc:
        return f"[ERROR] {exc}"


def _list_todos(status: str = "open") -> str:
    try:
        from jarvis.smart_todo import SmartTodo
        vault_path = Path.home() / "Documents" / "vault"
        return SmartTodo(vault_path).list_items(status)
    except Exception as exc:
        return f"[ERROR] {exc}"


def _snapshot_workspace() -> str:
    try:
        from jarvis.desktop.workspace_memory import WorkspaceMemory
        return WorkspaceMemory().snapshot()
    except Exception as exc:
        return f"[ERROR] {exc}"


def _restore_workspace(snapshot_json: str) -> str:
    try:
        import json
        from jarvis.desktop.workspace_memory import WorkspaceMemory
        snapshot = json.loads(snapshot_json)
        return WorkspaceMemory().restore(snapshot)
    except Exception as exc:
        return f"[ERROR] {exc}"


def _launch_best(query: str) -> str:
    try:
        from jarvis.desktop.smart_launcher import smart_launch
        return smart_launch(query)
    except Exception as exc:
        return f"[ERROR] {exc}"


def _recent_clipboard(n: int = 20) -> str:
    try:
        from jarvis.desktop.clipboard_history import ClipboardHistory
        return ClipboardHistory().get_recent(n)
    except Exception as exc:
        return f"[ERROR] {exc}"


def _recent_notifications(n: int = 10) -> str:
    try:
        from jarvis.desktop.notification_triage import NotificationTriage
        return NotificationTriage().recent(n)
    except Exception as exc:
        return f"[ERROR] {exc}"


def _archive_screenshots() -> str:
    try:
        from jarvis.desktop.screenshot_manager import ScreenshotManager
        count = ScreenshotManager().archive()
        return f"[SCREENSHOTS] Archived {count} file(s)"
    except Exception as exc:
        return f"[ERROR] {exc}"


def _window_timeline(hours: int = 24) -> str:
    try:
        from jarvis.desktop.window_logger import WindowLogger
        since = datetime.now() - timedelta(hours=hours)
        return WindowLogger().get_timeline(since)
    except Exception as exc:
        return f"[ERROR] {exc}"


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
    "obsidian_create": _obsidian_create,
    "obsidian_read": _obsidian_read,
    "obsidian_search": _obsidian_search,
    "obsidian_daily": _obsidian_daily,
    "skill_run": _skill_run,
    "skill_list": _skill_list,
    "memdir_add": _memdir_add,
    "memdir_search": _memdir_search,
    "list_apps": _list_apps,
    "search_apps": _search_apps,
    "launch_app": _launch_app,
    "focus_app": _focus_app,
    "mcp_start": _mcp_start,
    "mcp_status": _mcp_status,
    "proactive_start": _proactive_start,
    "proactive_stop": _proactive_stop,
    "autoskill_review": _autoskill_review,
    "autoskill_prune": _autoskill_prune,
    "markitdown_convert": _markitdown_convert,
    "file_search": _file_search,
    "universal_search": _universal_search,
    "ingest_pdf": _ingest_pdf,
    "organize_downloads": _organize_downloads,
    "fetch_rss_digest": _fetch_rss_digest,
    "add_todo": _add_todo,
    "list_todos": _list_todos,
    "snapshot_workspace": _snapshot_workspace,
    "restore_workspace": _restore_workspace,
    "launch_best": _launch_best,
    "recent_clipboard": _recent_clipboard,
    "recent_notifications": _recent_notifications,
    "archive_screenshots": _archive_screenshots,
    "window_timeline": _window_timeline,
    "screen_pointer": lambda args: __import__("jarvis.vision_agent", fromlist=["click_element"]).click_element(args.get("element", "")),
    "screen_explain": lambda args: __import__("asyncio").run(__import__("jarvis.vision_tool", fromlist=["capture_and_ask"]).capture_and_ask("Explain what you see in this screen region.")),
    "focus_mode": _focus_mode,
}
