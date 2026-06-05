"""Tests for queue_worker.py."""
from queue_worker import main


def test_main_imports():
    # main() runs an event loop, so just verify it is callable
    assert callable(main)
