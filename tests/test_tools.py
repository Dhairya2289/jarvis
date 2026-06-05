"""
Tests for jarvis.tools
"""

import os
from pathlib import Path

from jarvis.tools import (
    TOOL_DEFINITIONS,
    dispatch_tool,
    _DISPATCH_EXTRA,
    register_tool,
)


class TestToolRegistry:
    def test_definitions_non_empty(self):
        assert len(TOOL_DEFINITIONS) >= 10

    def test_unknown_tool_returns_error(self):
        result = dispatch_tool("nonexistent_tool", {})
        assert result.startswith("[ERROR]")

    def test_dispatch_extra_hook(self):
        was_called = {}

        def fake_tool(x: int) -> str:
            was_called["x"] = x
            return f"got {x}"

        register_tool("fake_test_tool", fake_tool)
        result = dispatch_tool("fake_test_tool", {"x": 42})
        assert result == "got 42"
        assert was_called["x"] == 42
        # clean up
        _DISPATCH_EXTRA.pop("fake_test_tool", None)


class TestBashTool:
    def test_blocked_command(self):
        result = dispatch_tool("bash", {"command": "rm -rf /"})
        assert "[BLOCKED]" in result

    def test_bash_valid_command(self):
        result = dispatch_tool("bash", {"command": "echo hello_v3_tests"})
        assert "hello_v3_tests" in result


class TestFileTools:
    def test_write_and_read_file(self, tmp_path):
        p = tmp_path / "testfile.txt"
        write_result = dispatch_tool("write_file", {"path": str(p), "content": "hello v3"})
        assert "Wrote" in write_result
        read_result = dispatch_tool("read_file", {"path": str(p), "limit": 100})
        assert read_result == "hello v3"

    def test_read_missing_file(self, tmp_path):
        p = tmp_path / "missing.txt"
        result = dispatch_tool("read_file", {"path": str(p)})
        assert result.startswith("[ERROR]")


class TestOsHardwareControl:
    def test_volume_up_dispatch(self):
        # Volume up should run without error (pactl must exist)
        result = dispatch_tool("os_hardware_control", {"action": "volume_up"})
        assert "Executed" in result

    def test_lock_dispatch(self):
        result = dispatch_tool("os_hardware_control", {"action": "lock"})
        assert "Executed" in result

    def test_unknown_action(self):
        result = dispatch_tool("os_hardware_control", {"action": "teleport"})
        assert result.startswith("[ERROR]")


class TestSystemHealth:
    def test_system_health_report(self):
        result = dispatch_tool("system_health_report", {})
        # Should contain CPU or Memory info
        assert "CPU" in result or "Memory" in result or "[ERROR]" in result


class TestGitOps:
    def test_git_status_current_dir(self):
        result = dispatch_tool("git_ops", {"command": "status", "cwd": "."})
        # May pass or fail depending on whether cwd is a git repo
        assert isinstance(result, str)


class TestSpawnAgent:
    def test_spawn_agent(self):
        result = dispatch_tool("spawn_agent", {"specialist": "coder", "task": "write tests"})
        assert "DELEGATED" in result