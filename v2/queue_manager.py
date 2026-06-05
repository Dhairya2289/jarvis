"""JARVIS Autonomous Queue Manager

Handles persistent task queuing for background execution.
"""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

from config import BASE_DIR

_log = logging.getLogger(__name__)

QUEUE_FILE: Final[Path] = BASE_DIR / "task_queue.jsonl"

NotifyCallback = Callable[[str, str, str], Any] | None
"""Signature: notify(user_id, task_text, result_text) -> Any"""


def add_to_queue(
    task: str,
    user_id: str,
    *,
    interface: str = "telegram",
) -> int:
    """Add a task to the persistent queue.

    Returns:
        The generated task ID.
    """
    entry = {
        "id": int(time.time() * 1000),
        "ts_added": datetime.now(timezone.utc).isoformat(),
        "task": task,
        "user_id": user_id,
        "interface": interface,
        "status": "pending",
    }
    try:
        with open(QUEUE_FILE, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        _log.error("Could not append to queue file: %s", exc)
        raise
    _log.info("Task #%d queued for %s", entry["id"], user_id)
    return entry["id"]


def list_queue(*, status: str = "pending") -> list[dict[str, Any]]:
    """List tasks matching *status*.

    Returns:
        List of task dicts (empty if queue file does not exist).
    """
    if not QUEUE_FILE.exists():
        return []
    tasks: list[dict[str, Any]] = []
    try:
        with open(QUEUE_FILE, "r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    tasks.append(json.loads(line))
                except json.JSONDecodeError:
                    _log.warning("Skipping corrupt queue line")
    except OSError as exc:
        _log.error("Could not read queue file: %s", exc)
    return [t for t in tasks if t.get("status") == status]


def mark_completed(task_id: int, status: str = "completed") -> None:
    """Update the status of a single queue entry in-place."""
    if not QUEUE_FILE.exists():
        return
    lines: list[str] = []
    updated = False
    try:
        with open(QUEUE_FILE, "r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    lines.append(line)
                    continue
                if data.get("id") == task_id:
                    data["status"] = status
                    data["ts_finished"] = datetime.now(timezone.utc).isoformat()
                    updated = True
                lines.append(json.dumps(data, ensure_ascii=False) + "\n")
        if updated:
            with open(QUEUE_FILE, "w", encoding="utf-8") as fh:
                fh.writelines(lines)
    except OSError as exc:
        _log.error("Could not update queue file: %s", exc)
        raise


def process_queue(
    *,
    notify_callback: NotifyCallback = None,
) -> int:
    """Execute all pending tasks.

    Args:
        notify_callback: Optional callback invoked with
            ``(user_id, task_text, result_text)`` when a task finishes.

    Returns:
        Number of tasks successfully processed.
    """
    pending = list_queue()
    if not pending:
        _log.debug("Queue is empty")
        return 0

    count = 0
    for item in pending:
        task_id = item["id"]
        task_text: str = item.get("task", "")
        user_id: str = item.get("user_id", "")

        mark_completed(task_id, "processing")

        result: str | None = None
        try:
            from agent import run_agent
            result = run_agent(task_text, session_id=f"queue_{user_id}")
        except Exception as exc:
            _log.error("Queue task %d failed: %s", task_id, exc, exc_info=True)
            mark_completed(task_id, f"failed: {exc}")
            continue

        # Notify via callback if provided (breaks circular dep with telegram_bot)
        if notify_callback is not None:
            try:
                notify_callback(user_id, task_text, result)
            except Exception as exc:
                _log.warning(
                    "Notify callback for task %d failed: %s", task_id, exc
                )
        else:
            _log.info("Queue task %d completed (no notifier)", task_id)

        mark_completed(task_id, "completed")
        count += 1

    _log.info("Processed %d/%d queued tasks", count, len(pending))
    return count


__all__ = [
    "add_to_queue",
    "list_queue",
    "mark_completed",
    "process_queue",
    "NotifyCallback",
]
