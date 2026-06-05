"""Tests for daemon module."""
from __future__ import annotations

import sys
from pathlib import Path

# sys.path hack removed — use PYTHONPATH=. or pip install -e .

from jarvis.daemon import _should_trigger


def test_trigger_cooldown():
    assert _should_trigger("test_key", cooldown=300) is True
    assert _should_trigger("test_key", cooldown=300) is False
