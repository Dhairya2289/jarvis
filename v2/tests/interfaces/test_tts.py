"""Tests for tts.py."""
from tts import _clean_text, speak_espeak


def test_clean_text_strips_markdown():
    raw = "# Hello **world** [link](http://x.com)"
    assert _clean_text(raw) == "Hello world"


def test_espeak_fallback():
    result = speak_espeak("test")
    assert "Spoken" in result or "Notification fallback" in result
