"""JARVIS Fast-Path Router — Microsecond Execution

Handles common OS commands and queries locally without hitting an LLM,
reducing latency from seconds to milliseconds.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Final

import automation_hub

_log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
#  Command aliases
# ═════════════════════════════════════════════════════════==
_VOLUME_UP_ALIASES: Final[frozenset[str]] = frozenset({
    "volume up", "increase volume", "louder",
})
_VOLUME_DOWN_ALIASES: Final[frozenset[str]] = frozenset({
    "volume down", "decrease volume", "quieter",
})
_MUTE_ALIASES: Final[frozenset[str]] = frozenset({
    "mute", "silence",
})
_LOCK_ALIASES: Final[frozenset[str]] = frozenset({
    "lock", "lock screen", "lock the computer",
})
_SUSPEND_ALIASES: Final[frozenset[str]] = frozenset({
    "suspend", "sleep",
})
_TIME_ALIASES: Final[frozenset[str]] = frozenset({
    "time", "what time is it", "current time",
})
_DATE_ALIASES: Final[frozenset[str]] = frozenset({
    "date", "what is the date", "today's date",
})
_HEALTH_ALIASES: Final[frozenset[str]] = frozenset({
    "health", "system health", "status", "how are you",
})
_MEDIA_PLAY_ALIASES: Final[frozenset[str]] = frozenset({
    "play", "resume",
})
_MEDIA_PAUSE_ALIASES: Final[frozenset[str]] = frozenset({
    "pause", "stop",
})
_MEDIA_NEXT_ALIASES: Final[frozenset[str]] = frozenset({
    "next", "skip",
})
_MEDIA_PREV_ALIASES: Final[frozenset[str]] = frozenset({
    "previous", "back",
})


def execute_fast_path(task: str) -> str | None:
    """Check if *task* can be handled locally.

    Returns the result string if handled, ``None`` otherwise.
    """
    t = task.lower().strip().strip("!").strip("?")

    if t in _VOLUME_UP_ALIASES:
        return automation_hub.execute_hardware("volume_up")
    if t in _VOLUME_DOWN_ALIASES:
        return automation_hub.execute_hardware("volume_down")
    if t in _MUTE_ALIASES:
        return automation_hub.execute_hardware("mute_toggle")
    if t in _LOCK_ALIASES:
        return automation_hub.execute_hardware("lock")
    if t in _SUSPEND_ALIASES:
        return automation_hub.execute_hardware("suspend")

    if t in _TIME_ALIASES:
        return f"It is currently {datetime.now().strftime('%H:%M:%S')}."
    if t in _DATE_ALIASES:
        return f"Today is {date.today().strftime('%A, %B %d, %Y')}."
    if t in _HEALTH_ALIASES:
        return automation_hub.execute_resource_report()

    if t in _MEDIA_PLAY_ALIASES:
        return automation_hub.execute_media("play")
    if t in _MEDIA_PAUSE_ALIASES:
        return automation_hub.execute_media("pause")
    if t in _MEDIA_NEXT_ALIASES:
        return automation_hub.execute_media("next")
    if t in _MEDIA_PREV_ALIASES:
        return automation_hub.execute_media("previous")

    return None


__all__ = ["execute_fast_path"]
