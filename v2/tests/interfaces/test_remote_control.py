"""Tests for remote_control.py."""
from remote_control import execute_remote_bash, execute_remote_health


def test_remote_bash_no_paramiko(monkeypatch):
    monkeypatch.setattr("builtins.__import__", lambda *a, **kw: (_ for _ in ()).throw(ImportError("paramiko")))
    result = execute_remote_bash("host", "ls")
    assert "paramiko" in result
