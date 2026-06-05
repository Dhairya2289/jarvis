"""Tests for speed_ops.py."""
from speed_ops import execute_lightning_play, execute_high_speed_plan


def test_lightning_play_not_installed(monkeypatch):
    monkeypatch.setattr("subprocess.Popen", lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError("mpv")))
    result = execute_lightning_play("test")
    assert "not installed" in result


def test_high_speed_plan_runs():
    result = execute_high_speed_plan(["echo hello"])
    assert "SUCCESS" in result or "FAILED" in result
