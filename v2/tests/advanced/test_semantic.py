"""Tests for semantic.py."""
from semantic import execute_semantic_scan


def test_scan_returns_string():
    result = execute_semantic_scan()
    assert isinstance(result, str)
