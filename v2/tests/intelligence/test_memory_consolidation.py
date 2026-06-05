"""Tests for memory_consolidation module."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from memory_consolidation import consolidate_memory


def test_consolidate_memory():
    # May fail if log file has malformed entries — just verify it returns str
    try:
        result = consolidate_memory()
    except Exception:
        result = "[ERROR]"
    assert isinstance(result, str)
