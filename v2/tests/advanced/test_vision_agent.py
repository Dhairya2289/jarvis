"""Tests for vision_agent.py."""
from vision_agent import _res_from_hyprctl


def test_res_from_hyprctl():
    w, h = _res_from_hyprctl()
    assert isinstance(w, int) and isinstance(h, int)
    assert w > 0 and h > 0
