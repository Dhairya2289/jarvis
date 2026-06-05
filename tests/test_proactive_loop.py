"""Tests for proactive loop."""
from __future__ import annotations

import pytest
from jarvis.proactive_loop import ProactiveLoop


class TestProactiveLoop:
    def test_init(self):
        pl = ProactiveLoop(interval_s=30)
        assert pl.interval_s == 30
        assert not pl.is_running()

    def test_sensors_returns_dict(self):
        pl = ProactiveLoop()
        state = pl._sensors()
        assert isinstance(state, dict)
        assert "ts" in state

    def test_start_stop(self):
        pl = ProactiveLoop(interval_s=1)
        pl.start()
        assert pl.is_running()
        pl.stop()
        assert not pl.is_running()

    def test_decide_returns_none_on_stable_state(self):
        pl = ProactiveLoop()
        state = {"cpu": 10.0, "mem": 4.0, "window": "kitty"}
        pl._last_state = state.copy()
        assert pl._decide(state) is None

    def test_decide_detects_cpu_spike(self):
        pl = ProactiveLoop()
        pl._last_state = {"cpu": 20.0, "mem": 4.0, "window": "kitty"}
        state = {"cpu": 95.0, "mem": 4.0, "window": "kitty"}
        result = pl._decide(state)
        assert result is not None
        assert "cpu" in result.lower()

    def test_decide_detects_window_change(self, monkeypatch):
        from jarvis import proactive_loop as _pl
        from jarvis.context_engine import Intent
        monkeypatch.setattr(
            _pl,
            "classify_intent",
            lambda q: Intent("system", 0.8, "tools"),
        )
        pl = ProactiveLoop()
        pl._last_state = {"window": "kitty"}
        state = {"cpu": 10.0, "mem": 4.0, "window": "firefox"}
        result = pl._decide(state)
        assert result is not None
        assert "firefox" in result
