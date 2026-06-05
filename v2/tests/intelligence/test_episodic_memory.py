"""Tests for episodic_memory module."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from episodic_memory import retrieve_past_task, store_successful_task


def test_retrieve_empty():
    result = retrieve_past_task("buy a rocket")
    assert isinstance(result, str)


def test_store_and_retrieve():
    store_successful_task("test task", ["action1", "action2"])
    result = retrieve_past_task("test task")
    assert isinstance(result, str)
