"""Tests for automation_hub.py."""
from automation_hub import _run, execute_media, execute_process


def test_run_missing_command():
    result = _run(["nonexistent_command_xyz"])
    assert "Missing command" in result


def test_media_unknown_action():
    result = execute_media("rewind")
    assert "Unknown media action" in result


def test_process_unknown_action():
    result = execute_process("freeze", "foo")
    assert "Unknown process action" in result
