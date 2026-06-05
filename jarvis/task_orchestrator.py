#!/usr/bin/env python3
"""JARVIS Task Orchestrator

Manages pending tasks, prevents duplicates, and schedules async work
with optional Telegram notifications and digests.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any

from jarvis.config import BASE_DIR, LOG_LEVEL
from modules.improvement.fuzzy_matcher import rate_limited, fuzzy_duplicate_check

_log = logging.getLogger(__name__)
_log.setLevel(getattr(logging, LOG_LEVEL, logging.DEBUG))

_TASKS_FILE: Path = BASE_DIR / "scheduled_tasks.json"

_DUPLICATE_WINDOW_HOURS: int = 2


class DuplicateTaskError(Exception):
    """Raised when a dangerously similar task is already pending."""

    pass


class Task:
    """Represents a user-facing task item."""

    def __init__(
        self,
        description: str,
        *,
        priority: str = "normal",
        context: str = "",
        tags: list[str] | None = None,
        eta: str | None = None,
    ) -> None:
        self.id: str = str(uuid.uuid4())[:8]
        self.description: str = description
        self.priority: str = priority.lower()
        self.context: str = context
        self.tags: list[str] = list(tags) if tags else []
        self.eta: str | None = eta
        self.completed: bool = False
        self.created_at: str = dt.datetime.now().isoformat()
        self.notified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "priority": self.priority,
            "context": self.context,
            "tags": self.tags,
            "eta": self.eta,
            "completed": self.completed,
            "created_at": self.created_at,
            "notified": self.notified,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        t = cls(
            description=data["description"],
            priority=data.get("priority", "normal"),
            context=data.get("context", ""),
            tags=data.get("tags"),
            eta=data.get("eta"),
        )
        t.id = data["id"]
        t.completed = data.get("completed", False)
        t.created_at = data.get("created_at", dt.datetime.now().isoformat())
        t.notified = data.get("notified", False)
        return t


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def _load_raw() -> list[dict[str, Any]]:
    """Return the raw list of task dicts on disk (or [])."""
    if not _TASKS_FILE.exists():
        return []
    try:
        return json.loads(_TASKS_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        _log.warning("Could not load tasks: %s", exc)
        return []


def _load_all() -> list[Task]:
    """Return list of Task objects."""
    return [Task.from_dict(d) for d in _load_raw()]


def _save_all(tasks: list[Task]) -> None:
    """Persist tasks to JSON file atomically."""
    payload = [t.to_dict() for t in tasks]
    tmp = _TASKS_FILE.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=4), encoding="utf-8")
        tmp.replace(_TASKS_FILE)
    except OSError as exc:
        _log.error("Failed to save tasks: %s", exc, exc_info=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@rate_limited()
def add_task(
    description: str,
    *,
    priority: str = "normal",
    context: str = "",
    tags: list[str] | None = None,
    eta: str | None = None,
) -> str:
    """Add a new task; raises DuplicateTaskError if too similar a task
    exists within the duplicate window."""
    tasks = _load_all()

    # Deduplicate against pending tasks created recently
    for t in tasks:
        if t.completed:
            continue
        if not _within_duplicate_window(t.created_at):
            continue
        is_dup, _ = fuzzy_duplicate_check(description, t.description)
        if is_dup:
            raise DuplicateTaskError(
                f"⚠️ Duplicate detected:  '{t.description}'"
                f"\nIf different, rephrase or add more detail."
            )

    task = Task(
        description=description,
        priority=priority,
        context=context,
        tags=tags,
        eta=eta,
    )
    tasks.append(task)
    _save_all(tasks)
    info = f"📋 Added {priority} task#{task.id} → {description}"
    _log.info(info)
    return info


def complete_task(task_id: str) -> str:
    """Mark task completed."""
    tasks = _load_all()
    for t in tasks:
        if t.id == task_id:
            t.completed = True
            _save_all(tasks)
            _log.info("Task %s completed", task_id)
            return f"✅ Task#{task_id} completed!"
    _log.warning("Task %s not found for completion", task_id)
    return f"❌ Task#{task_id} not found."


def list_tasks() -> str:
    """Return a human-readable task list."""
    tasks = _load_all()
    pending = [t for t in tasks if not t.completed]
    if not pending:
        return "📋 No active tasks."
    lines = ["⏳ Active tasks:"]
    for t in pending:
        tag_str = f" [tags: {', '.join(t.tags)}]" if t.tags else ""
        eta_str = f" (ETA: {t.eta})" if t.eta else ""
        lines.append(
            f"  [{t.priority.upper()}] #{t.id}: {t.description}{tag_str}{eta_str}"
        )
    return "\n".join(lines)


def list_all_tasks_json() -> str:
    """Return all tasks (including completed) as JSON string."""
    return json.dumps(
        [t.to_dict() for t in _load_all()], indent=2, default=str
    )


def get_high_priority_tasks() -> str:
    """Return only high-priority active tasks."""
    tasks = [t for t in _load_all() if not t.completed and t.priority == "high"]
    if not tasks:
        return "🎯 No high-priority tasks."
    return "🎯\n" + "\n".join(
        f"  #{t.id}: {t.description} [Context: {t.context}]" for t in tasks
    )


def mark_notified(task_id: str) -> str:
    """Mark a task as having been Telegram-notified."""
    tasks = _load_all()
    for t in tasks:
        if t.id == task_id:
            t.notified = True
            _save_all(tasks)
            _log.info("Task %s marked notified", task_id)
            return f"✅ Task#{task_id} marked as notified."
    _log.warning("Task %s not found for notification", task_id)
    return f"❌ Task#{task_id} not found."


def get_unnotified_tasks() -> list[Task]:
    """Return active tasks that haven't been notified yet."""
    return [t for t in _load_all() if not t.completed and not t.notified]


def delete_completed_and_archived() -> str:
    """Purge completed tasks older than 24 h."""
    tasks = _load_all()
    cutoff = dt.datetime.now() - dt.timedelta(days=1)
    kept = []
    purged = 0
    for t in tasks:
        if t.completed:
            try:
                created = dt.datetime.fromisoformat(t.created_at)
                if created >= cutoff:
                    kept.append(t)
                else:
                    purged += 1
            except Exception:
                purged += 1
        else:
            kept.append(t)
    _save_all(kept)
    _log.info("Purged %s completed tasks", purged)
    return f"🗑️  Purged {purged} completed tasks."


def send_daily_digest(chat_id: int | None = None) -> str:
    """Compile and optionally send a Telegram digest of tasks."""
    tasks = _load_all()
    pending = [t for t in tasks if not t.completed]
    completed_today = [
        t for t in tasks
        if t.completed and _is_created_today(t.created_at)
    ]
    lines = ["📝 Daily Task Digest"]
    lines.append("")
    if pending:
        lines.append("⏳ Pending:")
        for t in pending:
            tag_str = f" [tags: {', '.join(t.tags)}]" if t.tags else ""
            lines.append(f"  [{t.priority.upper()}] {t.description}{tag_str}")
    else:
        lines.append("✅ No pending tasks.")
    lines.append("")
    if completed_today:
        lines.append("✅ Completed today:")
        for t in completed_today:
            lines.append(f"  - {t.description}")
    else:
        lines.append("📭 No completions today.")

    digest = "\n".join(lines)
    if chat_id is not None:
        try:
            from modules.messaging.telegram_bot import send_message
            send_message(chat_id, digest)
        except Exception as exc:
            _log.warning("Digest Telegram send failed: %s", exc)
    return digest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _within_duplicate_window(created_at: str) -> bool:
    """Return True if created_at is within DUPLICATE_WINDOW_HOURS."""
    try:
        created = dt.datetime.fromisoformat(created_at)
        return dt.datetime.now() - created < dt.timedelta(hours=_DUPLICATE_WINDOW_HOURS)
    except Exception:
        return False


def _is_created_today(created_at: str) -> bool:
    """Return True if created_at is today (local time)."""
    try:
        created = dt.datetime.fromisoformat(created_at)
        return created.date() == dt.datetime.now().date()
    except Exception:
        return False


__all__ = [
    "add_task",
    "complete_task",
    "list_tasks",
    "list_all_tasks_json",
    "get_high_priority_tasks",
    "mark_notified",
    "get_unnotified_tasks",
    "delete_completed_and_archived",
    "send_daily_digest",
    "Task",
    "DuplicateTaskError",
]
