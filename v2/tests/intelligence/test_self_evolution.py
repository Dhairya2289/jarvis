"""Tests for self_evolution module."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from self_evolution import analyze_capability_gap


def test_analyze_capability_gap_smoke(monkeypatch):
    monkeypatch.setattr(
        "self_evolution.client.messages.create",
        lambda *a, **kw: type("R", (), {"content": [type("C", (), {"text": '{"name": null}'})()]})()
    )
    result = analyze_capability_gap("Some task that failed", "missing tool")
    assert isinstance(result, dict) or isinstance(result, str)
