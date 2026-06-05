"""Tests for swarm module."""
from __future__ import annotations

import sys
from pathlib import Path

# sys.path hack removed — use PYTHONPATH=. or pip install -e .

from jarvis.swarm import smart_delegate, SUB_MODELS


def test_sub_models_keys():
    assert "researcher" in SUB_MODELS
    assert "coder" in SUB_MODELS
    assert "critic" in SUB_MODELS


def test_smart_delegate_depth_guard():
    # Depth > 3 should fall back to operator without recursion
    result = smart_delegate("simple task", depth=3)
    assert isinstance(result, str)
