"""JARVIS TTS Engine

Primary: piper-tts (offline, high quality, neural)
Fallback: espeak-ng → desktop notification
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Final

from jarvis.config import BASE_DIR, PIPER_VOICE, TTS_ENGINE

_log = logging.getLogger(__name__)

_lock = threading.Lock()

PIPER_MODELS_DIR: Final[Path] = BASE_DIR / "piper_models"
PIPER_MODELS_DIR.mkdir(parents=True, exist_ok=True)


def _model_path() -> Path:
    return PIPER_MODELS_DIR / f"{PIPER_VOICE}.onnx"


def _config_path() -> Path:
    return PIPER_MODELS_DIR / f"{PIPER_VOICE}.onnx.json"


def ensure_piper_model() -> bool:
    """Auto-download piper model if missing."""
    if _model_path().exists():
        return True
    try:
        import subprocess
        base_url = (
            "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"
        )
        lang = PIPER_VOICE.split("-")[0].replace("_", "/")
        for suffix in (".onnx", ".onnx.json"):
            url = f"{base_url}/{lang}/{PIPER_VOICE}/{PIPER_VOICE}{suffix}"
            out = str(PIPER_MODELS_DIR / f"{PIPER_VOICE}{suffix}")
            subprocess.run(
                ["wget", "-q", "-O", out, url], check=True, timeout=120
            )
        _log.info("Downloaded piper model: %s", PIPER_VOICE)
        return True
    except Exception as exc:
        _log.warning("Piper model download failed: %s", exc)
        return False


def speak_piper(text: str) -> str:
    """Speak via piper-tts (neural, offline, high quality)."""
    if not shutil.which("piper"):
        return speak_espeak(text)
    if not ensure_piper_model():
        return speak_espeak(text)
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fh:
            wav_path = fh.name
        proc = subprocess.Popen(
            ["piper", "--model", str(_model_path()), "--output_file", wav_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        proc.communicate(input=text.encode("utf-8"), timeout=30)
        player = "paplay" if shutil.which("paplay") else "aplay"
        subprocess.run(
            [player, wav_path],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
        )
        os.unlink(wav_path)
        return "[TTS] Spoken via piper."
    except Exception as exc:
        _log.warning("piper failed, falling back to espeak: %s", exc)
        return speak_espeak(text)


def speak_espeak(text: str) -> str:
    """Fallback: espeak-ng."""
    try:
        subprocess.run(
            ["espeak-ng", "-v", "en-us", "-s", "165", "-a", "180", text],
            check=True,
            timeout=30,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return "[TTS] Spoken via espeak-ng."
    except Exception:
        # Last resort: desktop notification
        try:
            subprocess.run(
                ["notify-send", "-u", "normal", "-a", "Jarvis", "🔊 Jarvis", text[:200]]
            )
        except Exception:
            pass
        return "[TTS] Notification fallback."


def _clean_text(text: str) -> str:
    """Strip markdown and cap length before TTS."""
    clean = re.sub(r"\*+|`+|#+|\[.*?\]\(.*?\)", "", text)
    return clean.strip()[:500]


def speak(text: str, *, blocking: bool = True) -> str:
    """Thread-safe speak. blocking=False returns immediately."""
    clean = _clean_text(text)

    def _speak() -> None:
        with _lock:
            try:
                if TTS_ENGINE == "espeak":
                    speak_espeak(clean)
                else:
                    speak_piper(clean)
            except Exception as exc:
                _log.error("TTS speak failed: %s", exc, exc_info=True)

    if blocking:
        _speak()
        return "[TTS] Done."
    threading.Thread(target=_speak, daemon=True).start()
    return "[TTS] Speaking async."


def play_activation_chime() -> None:
    """Play the Google-Assistant-style activation beep."""
    try:
        import numpy as np
        import sounddevice as sd
        sr = 22050
        t = np.linspace(0, 0.15, int(sr * 0.15), False)
        tone = (
            np.sin(2 * np.pi * 440 * t) * 0.3
            + np.sin(2 * np.pi * 880 * t) * 0.15
        )
        tone *= np.linspace(1, 0, len(tone))
        sd.play(tone.astype(np.float32), sr, blocking=True)
    except Exception:
        _log.debug("Chime playback failed (ignoring)", exc_info=True)


__all__ = ["speak", "speak_piper", "speak_espeak", "play_activation_chime"]
