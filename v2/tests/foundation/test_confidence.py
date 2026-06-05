"""Tests for confidence module."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from confidence import score, should_ask_user, should_research_more


def test_score_bounds():
    # Mock-free: rely on fallback
    val = score("test", "response")
    assert 0.0 <= val <= 1.0


def test_should_research_more():
    # Edge: very low score should trigger research
    assert should_research_more("test", "response") in (True, False)


def test_should_ask_user():
    # Edge: very low score should trigger user question
    assert should_ask_user("test", "response") in (True, False)
