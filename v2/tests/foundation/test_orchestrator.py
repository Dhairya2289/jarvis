"""Tests for orchestrator module."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from orchestrator import classify_task, get_best_model, get_routing_report, record_outcome


def test_classify_task_code():
    assert classify_task("write a python script") == "code"


def test_classify_task_vision():
    assert classify_task("take a screenshot") == "vision"


def test_classify_task_speed():
    assert classify_task("a short answer please") == "speed"


def test_classify_task_default():
    assert classify_task("do something") == "logic"


def test_get_routing_report_empty():
    report = get_routing_report()
    assert isinstance(report, str)
    assert "No routing data" in report or "Report" in report


def test_record_outcome():
    # Smoke test — should not raise
    record_outcome("speed", "groq:llama-3.3-70b-versatile", True)
    record_outcome("speed", "groq:llama-3.3-70b-versatile", False)
