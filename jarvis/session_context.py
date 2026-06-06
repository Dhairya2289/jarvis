"""Last-seen memory — persist session state across restarts."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

STATE_PATH = Path.home() / ".jarvis" / "last_session.json"


def save_session_context(task: str = "", active_window: str = "") -> None:
    """Save current session state for next restart."""
    context = {
        "last_task": task,
        "last_active_window": active_window,
        "timestamp": datetime.now().isoformat(),
    }
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(context, indent=2))


def load_session_context() -> dict:
    """Load previous session context."""
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {}


def get_welcome_message() -> str:
    """Return a personalized welcome based on last session."""
    ctx = load_session_context()
    if not ctx:
        return "Welcome back."
    last = ctx.get("last_task", "")
    win = ctx.get("last_active_window", "")
    ts = ctx.get("timestamp", "")
    if ts:
        ts = ts[:16].replace("T", " ")
    if last and win:
        return (
            f"Welcome back. Last session you were working on "
            f"'{last[:40]}' ({win}) at {ts}."
        )
    return "Welcome back."
