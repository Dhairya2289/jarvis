"""Notification triage: read mako history or D-Bus for recent notifications."""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from jarvis.config import BASE_DIR

_log = logging.getLogger(__name__)

__all__ = [
    "NotificationTriage",
    "NotificationEntry",
    "classify_notification",
    "triage_notifications",
]

_MAKO_HISTORY_PATH = Path.home() / ".local" / "share" / "mako" / "history"


@dataclass
class NotificationEntry:
    """A single notification record."""
    app: str
    title: str
    body: str
    timestamp: str  # ISO-8601
    urgency: str = "normal"

    def to_dict(self) -> dict:
        return {
            "app": self.app,
            "title": self.title,
            "body": self.body,
            "timestamp": self.timestamp,
            "urgency": self.urgency,
        }


class NotificationTriage:
    """
    Read and summarise recent desktop notifications.

    Primary source: ``~/.local/share/mako/history`` (mako notification daemon).
    Fallback: D-Bus ``notify-send`` history (if available).

    Example
    -------
    >>> triage = NotificationTriage()
    >>> for n in triage.recent(10):
    ...     print(n.title, n.body)
    >>> print(triage.summarize())
    """

    def __init__(self, history_path: Optional[Path] = None) -> None:
        self.history_path = history_path or _MAKO_HISTORY_PATH

    def recent(self, n: int = 10) -> list[NotificationEntry]:
        """
        Return the *n* most recent notifications.
        """
        # Try mako history first
        entries = self._read_mako_history(n)
        if entries:
            return entries

        # Fallback: D-Bus
        return self._read_dbus(n)

    def summarize(self) -> str:
        """
        Return a human-readable summary of recent notifications.
        """
        entries = self.recent(20)
        if not entries:
            return "No recent notifications."

        # Group by app
        by_app: dict[str, list[NotificationEntry]] = {}
        for e in entries:
            by_app.setdefault(e.app, []).append(e)

        lines = ["## Notification Summary", ""]
        for app, items in by_app.items():
            lines.append(f"- **{app}**: {len(items)} notification{'s' if len(items) > 1 else ''}")
            for item in items[:3]:
                body_preview = item.body[:60] + ("..." if len(item.body) > 60 else "")
                lines.append(f"  - {item.title}: {body_preview}")

        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Private: mako history reader
    # ------------------------------------------------------------------ #

    def _read_mako_history(self, n: int) -> list[NotificationEntry]:
        """Parse mako JSON history file."""
        if not self.history_path.exists():
            _log.debug("Mako history not found at %s", self.history_path)
            return []

        try:
            content = self.history_path.read_text(encoding="utf-8", errors="replace")
            # Mako history is JSONL (one JSON object per line)
            lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
            entries: list[NotificationEntry] = []

            # Read from the end (newest first)
            for line in reversed(lines):
                if len(entries) >= n:
                    break
                try:
                    obj = json.loads(line)
                    entries.append(self._parse_mako_entry(obj))
                except json.JSONDecodeError:
                    continue

            return list(reversed(entries))  # chronological order
        except Exception as exc:
            _log.error("Failed to read mako history: %s", exc)
            return []

    @staticmethod
    def _parse_mako_entry(obj: dict) -> NotificationEntry:
        """Convert a mako JSON object to a NotificationEntry."""
        app = obj.get("app_name", obj.get("app", "unknown"))
        title = obj.get("summary", obj.get("title", ""))
        body = obj.get("body", "")
        timestamp = obj.get("timestamp", "")
        urgency = obj.get("urgency", "normal")

        # If timestamp is a Unix epoch float, convert
        if isinstance(timestamp, (int, float)):
            try:
                ts = datetime.fromtimestamp(float(timestamp))
                timestamp = ts.isoformat()
            except Exception:
                timestamp = str(timestamp)

        return NotificationEntry(
            app=app,
            title=title,
            body=body,
            timestamp=timestamp,
            urgency=urgency,
        )

    # ------------------------------------------------------------------ #
    # Private: D-Bus fallback
    # ------------------------------------------------------------------ #

    def _read_dbus(self, n: int) -> list[NotificationEntry]:
        """Try to read notifications via D-Bus."""
        try:
            result = subprocess.run(
                ["dbus-send", "--print-reply", "--dest=org.freedesktop.Notifications",
                 "/org/freedesktop/Notifications", "org.freedesktop.Notifications.GetCapabilities"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                return []
        except FileNotFoundError:
            _log.debug("dbus-send not available")
            return []
        except Exception as exc:
            _log.warning("D-Bus notification query failed: %s", exc)
            return []

        _log.debug("D-Bus notifications available but history not implemented — using empty list")
        return []


# ------------------------------------------------------------------ #
# Smart triage
# ------------------------------------------------------------------ #

_URGENT_KEYWORDS = [
    "meeting", "reminder", "alert", "failed", "error",
    "mentioned you", "overdue",
]

_SUPPRESS_KEYWORDS = [
    "promotion", "newsletter", "marketing", "ad", "sale", "unsubscribe",
]


def classify_notification(summary: str, body: str) -> str:
    """Classify a notification as *show*, *suppress*, or *defer*."""
    combined = (summary + " " + body).lower()
    if any(kw in combined for kw in _URGENT_KEYWORDS):
        return "show"
    if any(kw in combined for kw in _SUPPRESS_KEYWORDS):
        return "suppress"
    return "show"  # default


def triage_notifications(count: int = 10) -> dict[str, list[dict]]:
    """Return recent notifications bucketed by classification."""
    notifs = NotificationTriage().recent(count)
    result: dict[str, list[dict]] = {"show": [], "suppress": [], "defer": []}
    for n in notifs:
        category = classify_notification(n.title, n.body)
        result[category].append(n.to_dict())
    return result