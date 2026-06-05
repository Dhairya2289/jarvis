"""Tests for fast_path_router module."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from fast_path_router import execute_fast_path


def test_volume_up():
    result = execute_fast_path("volume up")
    assert result is not None


def test_time():
    result = execute_fast_path("time")
    assert result is not None
    assert "currently" in result


def test_date():
    result = execute_fast_path("date")
    assert result is not None
    assert "Today is" in result


def test_unknown_returns_none():
    result = execute_fast_path("launch a rocket to mars")
    assert result is None
