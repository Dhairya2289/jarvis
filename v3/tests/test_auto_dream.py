"""Tests for auto_dream module."""
from __future__ import annotations

from jarvis_v3.auto_dream import _read_state, _write_state, tick


class TestAutoDream:
    def test_read_state_default(self):
        state = _read_state()
        assert "last_consolidated_at" in state

    def test_write_and_read_roundtrip(self):
        from datetime import datetime
        state = {"last_consolidated_at": datetime(2026, 1, 1, 12, 0, 0).isoformat()}
        _write_state(state)
        restored = _read_state()
        assert restored["last_consolidated_at"] == state["last_consolidated_at"]

    def test_tick_time_gate_blocks(self, monkeypatch):
        monkeypatch.setattr(
            "jarvis_v3.auto_dream._run_consolidation",
            lambda: "[DREAM] Mock consolidation.",
        )
        # Force a recent last consolidated time so time gate blocks
        from datetime import datetime
        _write_state({"last_consolidated_at": datetime.now().isoformat()})
        result = tick()
        assert "Time gate" in result
