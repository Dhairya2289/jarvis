"""
CLI smoke tests for jarvis_v3.cli
"""

import sys


def test_imports():
    from jarvis_v3.cli import main, run_task, doctor, print_banner, _daemon_running
    assert callable(main)
    assert callable(run_task)
    assert callable(doctor)
    assert callable(print_banner)


def test_daemon_running_returns_bool():
    from jarvis_v3.cli import _daemon_running
    assert isinstance(_daemon_running(), bool)
