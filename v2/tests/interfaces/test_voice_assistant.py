"""Tests for voice_assistant.py."""
import numpy as np
from voice_assistant import detect_voice


def test_detect_voice_silence():
    silent = np.zeros(16000, dtype=np.int16)
    assert not detect_voice(silent)
