"""Tests for daemon module."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from daemon import _should_trigger


def test_trigger_cooldown():
    assert _should_trigger("test_key", cooldown=300) is True
    assert _should_trigger("test_key", cooldown=300) is False
