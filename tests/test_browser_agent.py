"""Tests for browser_agent.py."""
from jarvis.browser_agent import run_browser_task


def test_missing_playwright():
    result = run_browser_task("test", {"sequence": []})
    assert "playwright not installed" in result
