"""Tests for sandbox.py."""
import pytest
from sandbox import execute_sandboxed_bash, clear_sandbox, deploy_to_production
from config import SANDBOX_DIR


def test_blocked_command():
    result = execute_sandboxed_bash("rm -rf /")
    assert "BLOCKED" in result


def test_blocked_escape():
    result = execute_sandboxed_bash("cd / && ls")
    assert "BLOCKED" in result


def test_clear_sandbox():
    # Ensure a dummy file exists
    dummy = SANDBOX_DIR / "dummy.txt"
    dummy.write_text("hello")
    result = clear_sandbox()
    assert "Cleared" in result
    assert not dummy.exists()


def test_deploy_missing_source():
    result = deploy_to_production("nonexistent.txt", "/tmp/test.txt")
    assert "not found" in result
