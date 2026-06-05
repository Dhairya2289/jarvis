"""
Background Review Daemon — JARVIS V3 Post-Action Review
───────────────────────────────────────────────────────
Queues agent actions for asynchronous quality review.
Writes results to Obsidian notes or falls back to JSON logs.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from queue import Queue, Empty
from threading import Thread
from typing import Any

_LOG = logging.getLogger(__name__)

# ── Defaults ──────────────────────────────────────────────

DEFAULT_REVIEW_DIR = Path.home() / ".jarvis" / "reviews"
DEFAULT_OBSIDIAN_VAULT = Path.home() / ".jarvis" / "obsidian"
DEFAULT_REVIEW_INTERVAL = 300  # seconds


# ── Review Types ──────────────────────────────────────────

@dataclass
class ReviewResult:
    """Outcome of a post-action quality review."""
    grade: str       # "ok" | "slow" | "error"
    issues: list[str]
    suggestions: list[str]


# ── Action Log Shape ──────────────────────────────────────

# Expected input shape for submit():
ActionLog = dict[str, Any]   # requires: "action", "input", "output", "duration_ms"


# ── BackgroundReview ──────────────────────────────────────

class BackgroundReview:
    """
    Post-action review daemon.

    Actions submitted via :meth:`submit` are placed on an in-memory queue.
    A background worker drains the queue every ``review_interval`` seconds,
    grades each action, and writes the review to Obsidian (if available)
    or a JSON file in ``~/.jarvis/reviews/``.

    Thread-safe: all public methods are safe to call from any thread.
    """

    def __init__(
        self,
        review_interval: int = DEFAULT_REVIEW_INTERVAL,
        review_dir: Path | None = None,
        obsidian_vault: Path | None = None,
    ) -> None:
        self.review_interval = review_interval
        self.review_dir = (review_dir or DEFAULT_REVIEW_DIR).expanduser().resolve()
        self.obsidian_vault = (obsidian_vault or DEFAULT_OBSIDIAN_VAULT).expanduser().resolve()

        self._queue: Queue[ActionLog] = Queue()
        self._worker_thread: Thread | None = None
        self._stop_event = threading.Event()
        self._started = False
        self._started_lock = threading.Lock()

    # ── Review logic ────────────────────────────────────────

    def review_action(self, action_log: ActionLog) -> ReviewResult:
        """
        Grade a single action log entry using simple heuristics.

        No LLM involved — grading rules:

        - **error**: ``"error"`` appears in ``output.lower()``
        - **slow**: ``duration_ms > 5000``
        - **ok**: all other cases

        Each grade carries one or more suggestions.
        """
        output = action_log.get("output", "")
        duration_ms = action_log.get("duration_ms", 0)

        issues: list[str] = []
        suggestions: list[str] = []
        grade = "ok"

        output_lower = output.lower() if isinstance(output, str) else ""

        if "error" in output_lower:
            grade = "error"
            issues.append("Action output contained error signal")
            suggestions.append(
                "Check the error message and ensure all dependencies "
                "and inputs are valid before retrying"
            )
        elif duration_ms > 5000:
            grade = "slow"
            issues.append(f"Action took {duration_ms}ms (>5000ms threshold)")
            suggestions.append(
                "Consider optimising the request: reduce scope, "
                "use a faster model tier, or cache intermediate results"
            )

        if grade == "ok":
            suggestions.append("Action completed within acceptable parameters")

        _LOG.debug(
            "review_action grade=%r for action=%r (duration_ms=%d)",
            grade, action_log.get("action", "?"), duration_ms,
        )
        return ReviewResult(grade=grade, issues=issues, suggestions=suggestions)

    # ── Queue interface ────────────────────────────────────

    def submit(self, action_log: ActionLog) -> None:
        """
        Enqueue an action for asynchronous review.

        Args:
            action_log: dict with at least keys ``action``, ``input``,
                        ``output``, ``duration_ms``.
        """
        self._queue.put_nowait(action_log)
        _LOG.debug("Action queued for review: %s", action_log.get("action", "?"))

    # ── Daemon ─────────────────────────────────────────────

    def start(self) -> None:
        """Start the background review worker thread (idempotent)."""
        with self._started_lock:
            if self._started:
                return
            self._stop_event.clear()
            self._worker_thread = Thread(target=self._worker, daemon=True, name="BackgroundReview")
            self._worker_thread.start()
            self._started = True
            _LOG.info("BackgroundReview daemon started (interval=%ds)", self.review_interval)

    def stop(self) -> None:
        """Signal the worker to stop and wait for it to terminate."""
        if not self._started:
            return
        self._stop_event.set()
        if self._worker_thread is not None:
            self._worker_thread.join(timeout=5.0)
            self._worker_thread = None
        self._started = False
        _LOG.info("BackgroundReview daemon stopped")

    # ── Internal ───────────────────────────────────────────

    def _worker(self) -> None:
        """
        Background loop: poll the queue, drain pending items, review each,
        and write results.
        """
        while not self._stop_event.is_set():
            self._drain_queue()
            # Use polling so stop_event can interrupt promptly
            self._stop_event.wait(timeout=self.review_interval)

    def _drain_queue(self) -> None:
        """Pull all currently-queued actions and review them."""
        while True:
            try:
                action_log: ActionLog = self._queue.get_nowait()
            except Empty:
                break
            try:
                result = self.review_action(action_log)
                self._write_review(action_log, result)
            except Exception as exc:
                _LOG.error("Error during review of action %s: %s", action_log.get("action", "?"), exc)

    def _write_review(self, action_log: ActionLog, result: ReviewResult) -> None:
        """
        Persist a review result.

        Writes to an Obsidian daily note if the vault is available,
        otherwise falls back to ``~/.jarvis/reviews/{timestamp}.json``.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        action_name = action_log.get("action", "unknown").replace(" ", "_")

        # Try Obsidian daily note first
        if self.obsidian_vault.is_dir():
            try:
                self._write_obsidian_review(action_log, result, timestamp)
                return
            except Exception as exc:
                _LOG.warning("Failed to write Obsidian review, falling back to JSON: %s", exc)

        # Fallback: JSON file
        self._write_json_review(action_log, result, timestamp)

    def _write_obsidian_review(
        self, action_log: ActionLog, result: ReviewResult, timestamp: str
    ) -> None:
        """Append a review entry to today's Obsidian daily note."""
        daily_dir = self.obsidian_vault / "daily"
        daily_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now().strftime("%Y-%m-%d")
        daily_note_path = daily_dir / f"{date_str}.md"

        entry_lines = [
            "---",
            f"created: {timestamp}",
            f"tags: [review, {result.grade}]",
            "---",
            "",
            f"## Review: {action_log.get('action', '?')}",
            "",
            f"- **Grade**: {result.grade}",
            f"- **Input**: {action_log.get('input', '')[:200]}",
            f"- **Output**: {action_log.get('output', '')[:200]}",
            f"- **Duration**: {action_log.get('duration_ms', 0)}ms",
            "",
            f"- **Issues**: {', '.join(result.issues) if result.issues else 'none'}",
            f"- **Suggestions**: {'; '.join(result.suggestions)}",
            "",
        ]

        if daily_note_path.is_file():
            existing = daily_note_path.read_text()
            # Avoid duplicating entries within the same write session
            if f"## Review: {action_log.get('action', '?')}" not in existing:
                daily_note_path.write_text(existing + "\n".join(entry_lines))
        else:
            frontmatter = (
                "---\n"
                f"date: {date_str}\n"
                "tags: [daily]\n"
                "---\n\n"
            )
            daily_note_path.write_text(frontmatter + "\n".join(entry_lines))

        _LOG.debug("Review written to Obsidian: %s", daily_note_path)

    def _write_json_review(
        self, action_log: ActionLog, result: ReviewResult, timestamp: str
    ) -> None:
        """Write a review result as a standalone JSON file."""
        self.review_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{timestamp}_{action_log.get('action', 'unknown')}.json"
        review_path = self.review_dir / filename

        payload = {
            "timestamp": timestamp,
            "action": action_log.get("action"),
            "input": action_log.get("input"),
            "output": action_log.get("output"),
            "duration_ms": action_log.get("duration_ms", 0),
            "grade": result.grade,
            "issues": result.issues,
            "suggestions": result.suggestions,
        }
        review_path.write_text(json.dumps(payload, indent=2))
        _LOG.debug("Review written to JSON: %s", review_path)