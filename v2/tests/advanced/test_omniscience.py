"""Tests for omniscience.py."""
from omniscience import read_os_mind


def test_read_os_mind_returns_string():
    result = read_os_mind()
    assert isinstance(result, str)
    assert "OS_MIND" in result or "ACTIVE WINDOW" in result or "No data" in result
