"""Main voice command orchestrator."""

import json
import os
import subprocess
import sys
import time

from jarvis.voice.notifier import notify, update_notification
from jarvis.voice.recorder import record_audio
from jarvis.voice.transcriber import transcribe

STATE_FILE = "/tmp/jarvis_pill_state.json"
NOTIFY_ID_FILE = "/tmp/jarvis_voice_notify.id"


def _write_state(state: str, text: str = "", amplitude: float = 0.0) -> None:
    """Write current state to the pill state file."""
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({"state": state, "text": text, "amplitude": amplitude}, f)
    except OSError:
        pass


def _cleanup(pill_proc: subprocess.Popen | None) -> None:
    """Kill pill subprocess and remove temporary files."""
    if pill_proc is not None:
        try:
            pill_proc.terminate()
            pill_proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pill_proc.kill()
            pill_proc.wait(timeout=1)
        except Exception:
            pass
    for path in (STATE_FILE, NOTIFY_ID_FILE):
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def run_voice_mode() -> None:
    """Main voice loop:

    1. Notify: '🎤 Listening...' (persistent)
    2. Spawn pill.py subprocess (shows visualizer)
    3. Record audio (5 seconds)
    4. Update pill → '⚡ Transcribing...'
    5. Transcribe
    6. Notify: '💬 You said: "<text>"'
    7. Update pill → '⚡ JARVIS thinking...'
    8. Feed text to `process(text, voice_mode=True)`
    9. Update pill → '💬 Response' (show text)
    10. Kill pill, dismiss notification
    """
    pill_proc = None
    try:
        # 1. Persistent notification
        update_notification(NOTIFY_ID_FILE, "🎤 Listening...", "Speak now")

        # 2. Spawn pill
        _write_state("idle")
        pill_proc = subprocess.Popen(
            [sys.executable, "-m", "jarvis.voice.pill"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(0.5)  # give pill time to start

        # 3. Record
        _write_state("recording", "Listening...", amplitude=0.5)
        audio_path = record_audio(duration=5)

        # 4. Transcribing
        _write_state("processing", "⚡ Transcribing...")

        # 5. Transcribe
        text = transcribe(audio_path)
        if not text:
            notify("⚠ No speech detected", "", urgency="normal", transient=True)
            _write_state("done", "No speech detected")
            time.sleep(2)
            return

        # 6. Drag-to-explain: capture region and run vision agent
        transcript_lower = text.lower()
        if "what is this" in transcript_lower or "explain this" in transcript_lower:
            try:
                from jarvis.screen_region import capture_full
                from jarvis.agent import run_agent
                import asyncio
                img = capture_full()
                asyncio.run(run_agent(f"Explain what you see in this screenshot: {img}"))
            except Exception:
                pass  # Non-blocking; still process normally

        # 7. Notify what was said
        notify(f'💬 You said: "{text}"', "", transient=True)

        # 7. Thinking
        _write_state("processing", "⚡ JARVIS thinking...")

        # 8. Process via CLI engine
        from jarvis.cli_ui import process
        response = process(text, voice_mode=True)

        # 9. Show response
        display_text = response[:120] + "…" if len(response) > 120 else response
        _write_state("speaking", f"JARVIS: {display_text}")
        update_notification(NOTIFY_ID_FILE, "💬 JARVIS", display_text)
        time.sleep(5)

        # 10. Done
        _write_state("done", "")
        time.sleep(0.5)

    except RuntimeError as exc:
        notify("Voice mode error", str(exc), urgency="critical", transient=True)
        _write_state("done", str(exc))
        time.sleep(2)
    except Exception as exc:
        notify("Voice mode error", f"{type(exc).__name__}: {exc}", urgency="critical", transient=True)
        _write_state("done", f"Error: {exc}")
        time.sleep(2)
    finally:
        _cleanup(pill_proc)
