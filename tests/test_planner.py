"""Tests for planner module."""
from __future__ import annotations

import sys
from pathlib import Path

# sys.path hack removed — use PYTHONPATH=. or pip install -e .

from jarvis.planner import get_morning_briefing, get_todays_tasks


def test_get_todays_tasks():
    tasks = get_todays_tasks()
    assert isinstance(tasks, list)


def test_morning_briefing():
    result = get_morning_briefing()
    assert isinstance(result, str)
