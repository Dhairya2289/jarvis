"""JARVIS Voice Assistant — Google Assistant Style

Wake word → Activation chime → Record (VAD) → Whisper STT → Agent → TTS

Usage:
    python voice_assistant.py            # Run as foreground service
    python voice_assistant.py --hotkey   # Skip wake word, just hotkey-activated

Send SIGUSR1 to trigger manually:  kill -USR1 $(pgrep -f voice_assistant)
"""
from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import wave
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

import numpy as np
import requests
import sounddevice as sd

from config import (
    BASE_DIR,
    FCC_AUTH_TOKEN,
    FCC_BASE_URL,
    VOICE_BLOCK_SIZE,
    VOICE_CHANNELS,
    VOICE_SAMPLE_RATE,
    VOICE_SILENCE,
    WAKE_WORD,
)
from tts import play_activation_chime, speak

_log = logging.getLogger(__name__)

# ── State ─────────────────────────────────────────────────
_recording: threading.Event = threading.Event()
_shutdown: threading.Event = threading.Event()
_agent_func: Callable[[str], str] | None = None
ACTIVATION_LED: Final[Path] = BASE_DIR / ".voice_active"


# ═══════════════════════════════════════════════════════════
#  VAD (Voice Activity Detection)
# ═══════════════════════════════════════════════════════════
def detect_voice(chunk: np.ndarray, threshold: float = 0.015) -> bool:
    """Simple energy-based VAD. Works well for close-mic speech."""
    rms = np.sqrt(np.mean(chunk.astype(np.float32) ** 2) / (32768 ** 2))
    return bool(rms > threshold)


def record_until_silence(
    max_duration: float = 15.0,
    silence_gap: float | None = None,
) -> np.ndarray:
    """Record audio until silence (VAD) or *max_duration* reached."""
    silence_gap = silence_gap or VOICE_SILENCE
    frames: list[np.ndarray] = []
    silent_since: float | None = None
    started = time.time()

    ACTIVATION_LED.touch()

    def callback(indata: np.ndarray, *_: Any) -> None:
        frames.append(indata.copy())

    with sd.InputStream(
        samplerate=VOICE_SAMPLE_RATE,
        channels=VOICE_CHANNELS,
        dtype="int16",
        blocksize=VOICE_BLOCK_SIZE,
        callback=callback,
    ):
        while not _shutdown.is_set():
            time.sleep(0.05)
            if time.time() - started > max_duration:
                break
            if not frames:
                continue
            latest = frames[-1].flatten()
            if detect_voice(latest):
                silent_since = None
                continue
            if silent_since is None:
                silent_since = time.time()
            elif time.time() - silent_since > silence_gap:
                break

    ACTIVATION_LED.unlink(missing_ok=True)
    return np.concatenate(frames).flatten() if frames else np.array([], dtype=np.int16)


# ═══════════════════════════════════════════════════════════
#  STT via FCC / NIM Whisper
# ═══════════════════════════════════════════════════════════
def _audio_to_wav_bytes(audio: np.ndarray) -> bytes:
    """Convert int16 numpy array to WAV bytes."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fh:
        path = fh.name
    with wave.open(path, "wb") as wf:
        wf.setnchannels(VOICE_CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(VOICE_SAMPLE_RATE)
        wf.writeframes(audio.tobytes())
    data = Path(path).read_bytes()
    os.unlink(path)
    return data


def transcribe(audio: np.ndarray) -> str:
    """Send audio to FCC Whisper endpoint."""
    if len(audio) < VOICE_SAMPLE_RATE * 0.3:
        return ""
    wav_data = _audio_to_wav_bytes(audio)
    try:
        r = requests.post(
            f"{FCC_BASE_URL}/v1/audio/transcriptions",
            files={"file": ("audio.wav", wav_data, "audio/wav")},
            data={"model": "openai/whisper-large-v3", "language": "en"},
            headers={"Authorization": f"Bearer {FCC_AUTH_TOKEN}"},
            timeout=20,
        )
        return r.json().get("text", "").strip()
    except Exception as exc:
        _log.error("STT error: %s", exc)
        return ""


# ═══════════════════════════════════════════════════════════
#  Wake Word Detection
# ═══════════════════════════════════════════════════════════
_WAKE_VARIANTS: Final[list[str]] = [
    WAKE_WORD.lower(),
    WAKE_WORD.lower().replace(" ", ""),
    "hey jarvis",
    "jarvis",
    "hey javis",
    "javis",
]


def _contains_wake_word(transcript: str) -> bool:
    t = transcript.lower().strip()
    return any(v in t for v in _WAKE_VARIANTS)


def _extract_inline_command(transcript: str) -> str:
    """Remove wake word and return any trailing command."""
    cleaned = transcript.lower()
    for v in _WAKE_VARIANTS:
        cleaned = cleaned.replace(v, "")
    return cleaned.strip()


def _listen_for_wake_word() -> bool:
    """Passive listener: records 3-second chunks, transcribes, checks wake word."""
    while not _shutdown.is_set():
        frames: list[np.ndarray] = []

        def cb(indata: np.ndarray, *_: Any) -> None:
            frames.append(indata.copy())

        with sd.InputStream(
            samplerate=VOICE_SAMPLE_RATE,
            channels=VOICE_CHANNELS,
            dtype="int16",
            blocksize=VOICE_BLOCK_SIZE,
            callback=cb,
        ):
            time.sleep(2.5)

        if not frames:
            continue
        chunk = np.concatenate(frames).flatten()
        if not detect_voice(chunk):
            continue

        transcript = transcribe(chunk)
        if not transcript:
            continue

        if _contains_wake_word(transcript):
            cmd = _extract_inline_command(transcript)
            _log.info("Wake word detected. Inline command: %r", cmd)
            return True

    return False


# ═══════════════════════════════════════════════════════════
#  Main Voice Loop
# ═════════════════════════════════════════════════════════==
def _handle_voice_command() -> None:
    """Full cycle: chime → record → STT → agent → TTS."""
    _log.info("🎙️ Listening for command…")
    play_activation_chime()

    audio = record_until_silence(max_duration=12.0)
    if len(audio) == 0:
        speak("I didn't catch that. Try again.")
        return

    transcript = transcribe(audio)
    if not transcript:
        speak("Sorry, I couldn't understand. Please repeat.")
        return

    clean_task = _extract_inline_command(transcript) or transcript

    _log.info("📝 Heard: %s", transcript)
    _log.info("🧠 Processing: %s", clean_task)

    subprocess.Popen(
        ["notify-send", "-u", "normal", "-a", "Jarvis", "🎙️ Voice Command", clean_task[:100]],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if _agent_func is None:
        speak(f"I heard: {clean_task}. But the agent is not connected yet.")
        return

    try:
        result = _agent_func(clean_task)
    except Exception as exc:
        _log.error("Agent failed during voice command: %s", exc, exc_info=True)
        speak("Sorry, I encountered an error processing your request.")
        return

    lines = [l.strip() for l in result.split("\n") if l.strip() and not l.startswith("```")]
    tts_text = " ".join(lines[:3])[:400]
    if tts_text:
        speak(tts_text, blocking=False)
    _log.info("✅ Done: %s", result[:200])


def _signal_handler(_sig: int, _frame: Any) -> None:
    threading.Thread(target=_handle_voice_command, daemon=True).start()


def run_voice_loop(
    agent_fn: Callable[[str], str] | None = None,
    *,
    use_wake_word: bool = True,
) -> None:
    """Main entry point.

    Args:
        agent_fn: The agent callable (e.g. ``agent.run_agent``).
        use_wake_word: When False, only SIGUSR1 triggers.
    """
    global _agent_func
    _agent_func = agent_fn

    signal.signal(signal.SIGUSR1, _signal_handler)

    pid = os.getpid()
    pid_file = BASE_DIR / "voice.pid"
    pid_file.write_text(str(pid))
    _log.info(
        "Started (PID %d). Wake word: %r | Mode: %s",
        pid,
        WAKE_WORD,
        "active" if use_wake_word else "signal-only",
    )
    _log.info("Hyprland binding: bind = SUPER, V, exec, kill -USR1 %d", pid)

    speak("Jarvis voice assistant online.", blocking=False)

    try:
        if use_wake_word:
            while not _shutdown.is_set():
                if _listen_for_wake_word():
                    _handle_voice_command()
        else:
            while not _shutdown.is_set():
                time.sleep(0.5)
    except KeyboardInterrupt:
        _log.info("Shutdown signal received.")
    finally:
        pid_file.unlink(missing_ok=True)
        _shutdown.set()
        _log.info("Shutdown complete.")


def trigger_once(agent_fn: Callable[[str], str] | None = None) -> None:
    """Single voice capture + response. No loop."""
    global _agent_func
    _agent_func = agent_fn
    _handle_voice_command()


__all__ = [
    "run_voice_loop",
    "trigger_once",
    "detect_voice",
    "record_until_silence",
    "transcribe",
]
