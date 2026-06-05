"""Tests for auto-skill detector."""
from __future__ import annotations

import json
import pytest
from jarvis import auto_skills as _mod
from jarvis.auto_skills import AutoSkillDetector, ToolPattern, _canonical_args, _pattern_id


@pytest.fixture(autouse=True)
def tmp_patterns(monkeypatch, tmp_path):
    """Use a temp file for tool patterns so tests don't pollute ~/.jarvis."""
    monkeypatch.setattr(_mod, "PATTERNS_FILE", tmp_path / "patterns.json")
    (tmp_path / "patterns.json").write_text("{}")


class TestCanonicalArgs:
    def test_simple_args(self):
        assert _canonical_args({"b": 2, "a": 1}) == "a,b"

    def test_empty(self):
        assert _canonical_args({}) == ""


class TestPatternId:
    def test_stable(self):
        assert _pattern_id("bash", "command") == _pattern_id("bash", "command")
        assert len(_pattern_id("bash", "command")) == 12


class TestToolPattern:
    def test_roundtrip(self):
        p = ToolPattern("bash", "command", frequency=3)
        d = p.to_dict()
        assert d["tool_name"] == "bash"
        assert d["frequency"] == 3
        restored = ToolPattern.from_dict(d)
        assert restored.tool_name == p.tool_name


class TestAutoSkillDetector:
    def test_observe_creates_pattern(self):
        d = AutoSkillDetector(threshold=5)
        result = d.observe("bash", {"command": "echo hi"})
        assert result is None  # below threshold
        pid = _pattern_id("bash", "command")
        assert pid in d.patterns
        assert d.patterns[pid].frequency == 1

    def test_observe_crosses_threshold(self, monkeypatch):
        d = AutoSkillDetector(threshold=2)
        monkeypatch.setattr(d, "_maybe_create_skill", lambda pid: f"auto_bash_{pid[:6]}")
        d.observe("bash", {"command": "echo 1"})
        d.observe("bash", {"command": "echo 2"})
        result = d.observe("bash", {"command": "echo 3"})
        assert result is not None
        assert result.startswith("auto_bash")

    def test_review_output(self):
        d = AutoSkillDetector()
        d.observe("bash", {"command": "x"})
        text = d.review()
        assert "bash" in text
        assert "⏳ watching" in text

    def test_prune(self):
        d = AutoSkillDetector(decay_hours=0.00001)
        d.observe("bash", {"command": "x"})
        import time
        time.sleep(0.06)
        removed = d.prune()
        assert removed == 1
