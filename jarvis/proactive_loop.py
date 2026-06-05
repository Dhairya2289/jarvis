"""JARVIS Proactive Loop — Agent that watches your system and acts before you ask.

Inspired by Claude Code's proactive agent patterns.
Reimplemented for JARVIS to run entirely local (zero API cost).
"""
from __future__ import annotations

import datetime
import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Final

from jarvis.config import BASE_DIR
from jarvis.context_engine import classify_intent

_log = logging.getLogger(__name__)

CHECK_INTERVAL_S: Final[int] = 60
IDLE_THRESHOLD_S: Final[int] = 300


class ProactiveLoop:
    """Background daemon that watches system state and pro-actively suggests actions."""

    def __init__(self, interval_s: int = CHECK_INTERVAL_S) -> None:
        self.interval_s = interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_state: dict[str, float | str] = {}

    # ------------------------------------------------------------------
    #  Sensors
    # ------------------------------------------------------------------
    def _sensors(self) -> dict[str, float | str]:
        """Collect lightweight system signals."""
        state: dict[str, float | str] = {"ts": datetime.datetime.now().isoformat()}
        try:
            state["cpu"] = round(
                float(
                    subprocess.run(
                        ["top", "-bn1"], capture_output=True, text=True, timeout=3
                    )
                    .stdout.split("Cpu(s):")[1]
                    .split("%us")[0]
                    .strip()
                ),
                1,
            )
        except Exception:
            state["cpu"] = 0.0
        try:
            state["mem"] = round(
                float(
                    subprocess.run(
                        ["free"], capture_output=True, text=True, timeout=3
                    )
                    .stdout.split("Mem:")[1]
                    .split()[2]
                )
                / 1024 / 1024,
                1,
            )
        except Exception:
            state["mem"] = 0.0
        try:
            bat = subprocess.run(
                ["cat", "/sys/class/power_supply/BAT*/capacity"],
                capture_output=True,
                text=True,
                timeout=1,
            )
            state["battery"] = bat.stdout.strip()
        except Exception:
            state["battery"] = "?"
        # hyprland active window
        try:
            win = subprocess.run(
                ["hyprctl", "activewindow", "-j"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if win.returncode == 0:
                import json as _json
                data = _json.loads(win.stdout)
                state["window"] = data.get("class", "?")
                state["title"] = data.get("title", "?")[:80]
            else:
                state["window"] = "?"
        except Exception:
            state["window"] = "?"
        return state

    # ------------------------------------------------------------------
    #  Decision
    # ------------------------------------------------------------------
    def _decide(self, state: dict[str, float | str]) -> str | None:
        """Return a human-readable decision string, or None if nothing to do."""
        last = self._last_state
        cpu = float(state.get("cpu", 0.0))
        mem = float(state.get("mem", 0.0))
        window = str(state.get("window", ""))
        prev_window = str(last.get("window", ""))

        # 1. CPU spike
        if cpu > 90 and float(last.get("cpu", 0.0)) < 50:
            return f"system cpu high ({cpu}%)"

        # 2. Memory pressure
        if mem > 14 and float(last.get("mem", 0.0)) < 10:
            return f"system memory high ({mem:.1f} GB)"

        # 3. Window context switch → trigger context-engine
        if window != prev_window and window not in ("?", ""):
            intent = classify_intent(f"user switched to {window}")
            if intent.confidence > 0.4 and intent.category in ("system", "logic", "memory"):
                return f"user context {window} → {intent.category}"

        # 4. Battery low  
        bat = state.get("battery", "")
        if bat and bat.isdigit() and int(bat) < 15:
            return f"battery low ({bat}%)"

        return None

    # ------------------------------------------------------------------
    #  Action
    # ------------------------------------------------------------------
    def _act(self, decision: str, state: dict[str, float | str]) -> None:
        """Log to Obsidian and optionally notify."""
        msg = f"[{state.get('ts', '?')[:19]}] {decision}"
        _log.info("[PROACTIVE] %s", msg)
        try:
            from jarvis.obsidian_brain import ObsidianBrain
            ObsidianBrain().append_daily(f"[PROACTIVE] {msg}")
        except Exception:
            pass
        # If battery or high resource, send telegram
        if "battery" in decision or "high" in decision:
            try:
                from jarvis.telegram_bot import _push
                _push(f"⚠️ {msg}")
            except Exception:
                pass

    # ------------------------------------------------------------------
    #  Loop
    # ------------------------------------------------------------------
    def _tick(self) -> None:
        state = self._sensors()
        decision = self._decide(state)
        if decision:
            self._act(decision, state)
        self._last_state = state

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        _log.info("ProactiveLoop started (interval=%ds)", self.interval_s)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        _log.info("ProactiveLoop stopped")

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as exc:
                _log.error("Proactive tick failed: %s", exc, exc_info=True)
            self._stop.wait(self.interval_s)

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    loop = ProactiveLoop()
    loop.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        loop.stop()


__all__ = ["ProactiveLoop", "main"]
