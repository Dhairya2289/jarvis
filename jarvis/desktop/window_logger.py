"""Window title logger: poll hyprctl activewindow and record to JSONL."""

from __future__ import annotations

import json
import logging
import subprocess
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from jarvis.config import BASE_DIR

_log = logging.getLogger(__name__)

LOG_FILE = BASE_DIR / "desktop_window_log.jsonl"

__all__ = ["WindowLogger", "WindowEvent"]


@dataclass
class WindowEvent:
    """A single window focus event."""
    timestamp: str      # ISO-8601
    workspace: int
    title: str
    class_name: str
    pid: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def _run_hyprctl_activewindow() -> Optional[dict]:
    """Query hyprctl for the active window JSON, or None on failure."""
    try:
        result = subprocess.run(
            ["hyprctl", "activewindow", "-j"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            # No active window is not an error
            if "no" in result.stdout.lower() or "empty" in result.stdout.lower():
                return None
            _log.debug("hyprctl activewindow returned %d", result.returncode)
            return None
        if not result.stdout.strip():
            return None
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    except FileNotFoundError:
        _log.warning("hyprctl not found — is Hyprland running?")
    except subprocess.TimeoutExpired:
        _log.warning("hyprctl timed out")
    except Exception as exc:
        _log.debug("hyprctl activewindow error: %s", exc)
    return None


def _run_hyprctl_workspaces() -> Optional[dict]:
    """Query hyprctl for workspaces JSON, or None on failure."""
    try:
        result = subprocess.run(
            ["hyprctl", "workspaces", "-j"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None
        if not result.stdout.strip():
            return None
        return json.loads(result.stdout)
    except Exception:
        return None


class WindowLogger:
    """
    Poll ``hyprctl activewindow`` every 5 seconds and record focus events
    to a JSONL log file.

    Example
    -------
    >>> logger = WindowLogger()
    >>> event = logger.tick()   # call this periodically (e.g. every 5s)
    >>> if event:
    ...     print(event.title, event.class_name)
    >>> timeline = logger.get_timeline(since=datetime.now() - timedelta(hours=1))
    """

    def __init__(self, log_file: Optional[Path] = None) -> None:
        self.log_file = log_file or LOG_FILE
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self._last_event: Optional[WindowEvent] = None
        self._poller_running = False
        self._poller_thread: Optional[threading.Thread] = None

    def tick(self) -> Optional[WindowEvent]:
        """
        Poll the active window once and record if it changed.

        Returns the new :class:`WindowEvent` if the window changed since the
        last call, otherwise ``None``.
        """
        data = _run_hyprctl_activewindow()
        if data is None:
            self._last_event = None
            return None

        # Get workspace
        workspace_id = data.get("workspace", {}).get("id", 0)
        if workspace_id == 0:
            workspaces_data = _run_hyprctl_workspaces()
            if workspaces_data and isinstance(workspaces_data, list):
                active_ws = next(
                    (ws["id"] for ws in workspaces_data if ws.get("hasfocus")),
                    0,
                )
                workspace_id = active_ws

        event = WindowEvent(
            timestamp=datetime.now().isoformat(),
            workspace=workspace_id,
            title=data.get("title", ""),
            class_name=data.get("class", ""),
            pid=data.get("pid", 0),
        )

        # Only log if it changed
        if (
            self._last_event is None
            or self._last_event.title != event.title
            or self._last_event.class_name != event.class_name
            or self._last_event.workspace != event.workspace
        ):
            self._append(event)
            self._last_event = event
            return event

        return None

    def get_timeline(self, since: datetime) -> list[WindowEvent]:
        """
        Return all events recorded since *since*.
        """
        if not self.log_file.exists():
            return []

        events: list[WindowEvent] = []
        try:
            for line in self.log_file.read_text(encoding="utf-8", errors="replace").splitlines():
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                    ts = datetime.fromisoformat(obj["timestamp"])
                    if ts >= since:
                        events.append(WindowEvent(**obj))
                except (json.JSONDecodeError, KeyError, TypeError):
                    continue
        except Exception as exc:
            _log.error("Failed to read window log: %s", exc)

        return events

    def start_poller(self, interval: float = 5.0) -> None:
        """
        Start a background thread that calls :meth:`tick` every *interval* seconds.
        """
        if self._poller_running:
            _log.warning("Poller already running")
            return

        self._poller_running = True

        def _poll_loop() -> None:
            while self._poller_running:
                self.tick()
                time.sleep(interval)

        self._poller_thread = threading.Thread(target=_poll_loop, daemon=True)
        self._poller_thread.start()
        _log.info("Window logger poller started (interval=%.1fs)", interval)

    def stop_poller(self) -> None:
        """Stop the background poller."""
        self._poller_running = False
        if self._poller_thread:
            self._poller_thread.join(timeout=10)
            self._poller_thread = None
        _log.info("Window logger poller stopped")

    def event_count(self) -> int:
        """Return total number of events in the log."""
        if not self.log_file.exists():
            return 0
        try:
            return sum(1 for ln in self.log_file.read_text().splitlines() if ln.strip())
        except Exception:
            return 0

    # ------------------------------------------------------------------ #
    # Private
    # ------------------------------------------------------------------ #

    def _append(self, event: WindowEvent) -> None:
        """Append a JSON line to the log file."""
        try:
            with self.log_file.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event.to_dict()) + "\n")
            _log.debug("Window event: [%s] %s — %s", event.workspace, event.class_name, event.title)
        except Exception as exc:
            _log.error("Failed to write window event: %s", exc)