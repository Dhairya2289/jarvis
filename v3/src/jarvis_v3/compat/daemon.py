from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import threading
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

from jarvis_v3.config import BASE_DIR, TELEGRAM_TOKEN, ALLOWED_USER_IDS

_LOG = logging.getLogger(__name__)

STATE_FILE = BASE_DIR / "daemon_state.json"

# ── Telegram push ─────────────────────────────────────────
def _push(msg: str) -> None:
    """Send a message via Telegram bot.

    Args:
        msg: The message to send.
    """
    if not TELEGRAM_TOKEN or not ALLOWED_USER_IDS:
        _LOG.debug("[DAEMON] %s", msg)
        return
    # Import requests locally to avoid hard dependency if not used
    import requests
    for uid in ALLOWED_USER_IDS:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": uid, "text": msg, "parse_mode": "Markdown"},
                timeout=8
            )
        except Exception as e:
            _LOG.debug("Failed to send Telegram message to %s: %s", uid, e)

# ── Proactive context triggers ────────────────────────────
_last_triggers: dict[str, float] = {}

def _should_trigger(key: str, cooldown: int = 300) -> bool:
    """Rate-limit triggers to avoid spam.

    Args:
        key: The trigger key to check.
        cooldown: Minimum seconds between triggers (default 300).

    Returns:
        True if the trigger should fire, False otherwise.
    """
    last = _last_triggers.get(key, 0)
    if time.time() - last > cooldown:
        _last_triggers[key] = time.time()
        return True
    return False

def _on_window_open(class_name: str, title: str) -> None:
    """Proactive actions when specific apps open.

    Args:
        class_name: The window class name.
        title: The window title.
    """
    cl = class_name.lower()
    ti = title.lower()

    # PDF opened → offer to summarize
    if "evince" in cl or "okular" in cl or "zathura" in cl or ".pdf" in ti:
        if _should_trigger("pdf_open", 600):
            _push(
                f"📄 *PDF detected:* _{title[:60]}_\n\n"
                f"Send me: `summarize this PDF` to get a summary, "
                f"or `create anki cards from this PDF` to make flashcards."
            )

    # VS Code opened → offer context
    if "code" in cl or "cursor" in cl or "zed" in cl:
        if _should_trigger("editor_open", 1800):
            _push("💻 *Editor opened.* Need code review, refactoring, or a new feature? Just ask.")

    # Browser opened with study-related site
    if any(kw in ti for kw in ["iiser","cuet","nta","syllabus","exam","biology","chemistry"]):
        if _should_trigger("study_site", 900):
            _push(f"📚 *Study mode detected:* _{title[:60]}_\n"
                  f"Want me to take notes or create flashcards from this?")

    # Terminal opened → share OS context
    if "foot" in cl or "kitty" in cl or "alacritty" in cl or "wezterm" in cl:
        if _should_trigger("terminal_open", 1800):
            # Silently inject useful context — don't push for terminals
            pass

    # Generic Anticipatory Logic
    if _should_trigger("anticipatory", 3600):
        try:
            from anticipatory_engine import analyze_context_and_suggest
            suggestion = analyze_context_and_suggest(class_name, title)
            if suggestion:
                _push(f"💡 *Proactive Suggestion:* {suggestion}")
        except Exception as e:
            _LOG.debug("Anticipatory engine error: %s", e)

def _on_workspace_change(ws_id: int) -> None:
    """Trigger when workspace changes.

    Args:
        ws_id: The workspace ID.
    """
    # Extend as needed
    pass

# ── Hyprland IPC listener ─────────────────────────────────
async def _hypr_listener() -> None:
    """Listen for Hyprland IPC events and trigger proactive actions."""
    xdg = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    hyprland_instance = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "")

    if not hyprland_instance:
        _LOG.info("[DAEMON] Not running under Hyprland — IPC disabled.")
        return

    socket_path = f"{xdg}/hypr/{hyprland_instance}/.socket2.sock"
    if not Path(socket_path).exists():
        _LOG.info("[DAEMON] Hyprland socket not found: %s", socket_path)
        return

    _LOG.info("[DAEMON] Connected to Hyprland IPC: %s", socket_path)

    try:
        reader, _ = await asyncio.open_unix_connection(socket_path)
        while True:
            line = await reader.readline()
            if not line:
                break
            event = line.decode("utf-8", errors="ignore").strip()

            # Parse event: "eventName>>data"
            if ">>" in event:
                ev_type, ev_data = event.split(">>", 1)

                if ev_type == "openwindow":
                    # Format: address,workspace,class,title
                    parts = ev_data.split(",", 3)
                    if len(parts) >= 4:
                        wclass, wtitle = parts[2], parts[3]
                        threading.Thread(
                            target=_on_window_open,
                            args=(wclass, wtitle),
                            daemon=True
                        ).start()

                elif ev_type == "workspace":
                    try:
                        _on_workspace_change(int(ev_data))
                    except ValueError as e:
                        _LOG.debug("Invalid workspace data: %s", e)

    except Exception as e:
        _LOG.error("[DAEMON] IPC error: %s", e)

# ── Cron-style scheduler ──────────────────────────────────
async def _scheduler() -> None:
    """Run periodic tasks like morning briefing, dream cycle, etc."""
    morning_sent_date: Optional[date] = None
    dream_sent_date: Optional[date] = None
    failure_sent_date: Optional[date] = None
    health_check_ts: float = 0
    life_state_ts: float = 0

    while True:
        now = datetime.now()
        today = date.today()

        # Morning briefing at 7:30 AM
        if now.hour == 7 and now.minute >= 30 and morning_sent_date != today:
            morning_sent_date = today
            try:
                from planner import get_morning_briefing
                briefing = get_morning_briefing()
                _push(f"☀️ *Good morning!*\n\n{briefing}")
            except Exception as e:
                _LOG.error("[DAEMON] Morning briefing error: %s", e)

        # Dream Cycle (Memory Consolidation) on Sunday at 3 AM
        if now.weekday() == 6 and now.hour == 3 and dream_sent_date != today:
            dream_sent_date = today
            try:
                from memory_consolidation import consolidate_memory
                res = consolidate_memory()
                _push(f"🌙 *Dream Cycle Complete*\n{res}")
            except Exception as e:
                _LOG.error("[DAEMON] Dream cycle error: %s", e)

        # Failure Analysis (Self-Correction) on Saturday at 4 AM
        if now.weekday() == 5 and now.hour == 4 and failure_sent_date != today:
            failure_sent_date = today
            try:
                from failure_analyzer import analyze_failures
                res = analyze_failures()
                _push(f"🛠️ *Self-Correction Audit*\n{res}")
            except Exception as e:
                _LOG.error("[DAEMON] Failure analyzer error: %s", e)

        # Update life state every 30 minutes
        if time.time() - life_state_ts > 1800:
            life_state_ts = time.time()
            try:
                from life_state_manager import update_life_state
                update_life_state()
            except Exception as e:
                _LOG.error("[DAEMON] Life state update error: %s", e)

        # System health every 2 hours
        if time.time() - health_check_ts > 7200:
            health_check_ts = time.time()
            try:
                from world_model import _check_system_health
                alerts = _check_system_health()
                for alert in alerts:
                    _push(f"🖥️ *System Alert*\n{alert}")
            except Exception as e:
                _LOG.error("[DAEMON] System health check error: %s", e)

        await asyncio.sleep(60)   # Check every minute

# ── Main ──────────────────────────────────────────────────
async def main() -> None:
    """Main entry point for the JARVIS daemon."""
    _LOG.info("[DAEMON] JARVIS Daemon v2 starting...")

    # Write PID
    try:
        (BASE_DIR / "daemon.pid").write_text(str(os.getpid()))
        _LOG.debug("Wrote PID file")
    except Exception as e:
        _LOG.error("Failed to write PID file: %s", e)

    # Start world model monitoring in background thread
    try:
        import world_model
        world_model.start_background()
        _LOG.info("[DAEMON] World model started.")
    except Exception as e:
        _LOG.error("[DAEMON] World model failed: %s", e)

    # Load evolved tools
    try:
        from self_evolution import load_evolved_tools
        load_evolved_tools()
        _LOG.info("[DAEMON] Evolved tools loaded.")
    except Exception as e:
        _LOG.error("[DAEMON] Evolved tools load: %s", e)

    # Run IPC listener + scheduler concurrently
    try:
        await asyncio.gather(
            _hypr_listener(),
            _scheduler(),
        )
    except Exception as e:
        _LOG.error("[DAEMON] Error in main gather: %s", e)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _LOG.info("[DAEMON] Shutdown.")
        try:
            (BASE_DIR / "daemon.pid").unlink(missing_ok=True)
        except Exception as e:
            _LOG.debug("Failed to remove PID file: %s", e)
    except Exception as e:
        _LOG.error("[DAEMON] Unexpected error: %s", e)
        try:
            (BASE_DIR / "daemon.pid").unlink(missing_ok=True)
        except Exception:
            pass

# Define public API
__all__: List[str] = [
    "_push",
    "_should_trigger",
    "_on_window_open",
    "_on_workspace_change",
    "_hypr_listener",
    "_scheduler",
    "main",
]