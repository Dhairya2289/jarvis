"""Tests for planner module."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from planner import get_morning_briefing, get_todays_tasks


def test_get_todays_tasks():
    tasks = get_todays_tasks()
    assert isinstance(tasks, list)


def test_morning_briefing():
    result = get_morning_briefing()
    assert isinstance(result, str)
