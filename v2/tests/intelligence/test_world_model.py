"""Tests for world_model module."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from world_model import _check_system_health


def test_system_health_empty():
    alerts = _check_system_health()
    assert isinstance(alerts, list)
