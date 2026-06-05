"""Tests for queue_manager.py."""
import json
from pathlib import Path

import pytest

from jarvis.queue_manager import add_to_queue, list_queue, mark_completed


@pytest.fixture(autouse=True)
def patch_queue_file(tmp_path, monkeypatch):
    """Redirect queue writes to a temp file."""
    qfile = tmp_path / "queue.jsonl"
    monkeypatch.setattr("jarvis.queue_manager.QUEUE_FILE", qfile)
    yield qfile
    if qfile.exists():
        qfile.unlink()


def test_add_and_list(patch_queue_file):
    add_to_queue("task 1", user_id="test")
    q = list_queue()
    assert any("task 1" in item["task"] for item in q)


def test_mark_completed(patch_queue_file):
    add_to_queue("todo", user_id="test")
    q = list_queue()
    assert q
    tid = q[0]["id"]
    mark_completed(tid)
    assert all(item["status"] != "pending" for item in list_queue())
