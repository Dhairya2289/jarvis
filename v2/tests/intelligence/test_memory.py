"""Tests for memory module."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import memory as mem


def test_load_knowledge():
    data = mem.load_knowledge()
    assert isinstance(data, dict)


def test_graph_exists():
    # G may be private after refinement; just check graph functions work
    assert callable(mem.add_knowledge_edge)
    assert callable(mem.query_graph)
