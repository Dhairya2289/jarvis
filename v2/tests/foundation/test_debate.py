"""Tests for debate module."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from debate import should_debate, quick_debate


def test_should_debate_positive():
    assert should_debate("Which laptop should I buy?") is True


def test_should_debate_negative():
    assert should_debate("Play some music") is False


def test_quick_debate_mockable(monkeypatch):
    import debate
    monkeypatch.setattr(debate, "_query_parallel", lambda prompts: {"M1": "a"})
    monkeypatch.setattr(debate, "_query", lambda model, prompt, **kw: "best")
    result = quick_debate("Which laptop should I buy?")
    assert isinstance(result, str)
    assert "best" in result
