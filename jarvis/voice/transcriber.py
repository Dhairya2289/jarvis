"""Offline speech-to-text via Vosk."""

import json
import os
import tempfile
import wave

import vosk

MODEL_PATH = os.path.expanduser("~/.jarvis/models/vosk-model")

# Module-level cache for model instance
_model_instance = None


def _get_model():
    """Lazy-load and cache the Vosk model."""
    global _model_instance
    if _model_instance is None:
        if not os.path.exists(MODEL_PATH):
            raise RuntimeError(f"Vosk model not found at {MODEL_PATH}")
        _model_instance = vosk.Model(MODEL_PATH)
    return _model_instance


def transcribe_bytes(audio_bytes: bytes) -> str:
    """Transcribe raw audio bytes by writing to a temp WAV file."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        result = transcribe(tmp_path)
    finally:
        if 'tmp_path' in locals():
            os.unlink(tmp_path)
    return result


def transcribe(audio_path: str) -> str:
    """Transcribe WAV file using Vosk offline model.

    Returns transcribed text or empty string on failure.
    """
    try:
        wf = wave.open(audio_path, "rb")
    except Exception:
        return ""

    # Validate wave format
    if (
        wf.getnchannels() != 1
        or wf.getsampwidth() != 2
        or wf.getframerate() not in (8000, 16000)
    ):
        wf.close()
        return ""

    model = _get_model()
    rec = vosk.KaldiRecognizer(model, wf.getframerate())

    try:
        while True:
            data = wf.readframes(4096)
            if len(data) == 0:
                break
            rec.AcceptWaveform(data)
    finally:
        wf.close()

    result = rec.FinalResult()
    try:
        obj = json.loads(result)
        return obj.get("text", "")
    except json.JSONDecodeError:
        return ""
