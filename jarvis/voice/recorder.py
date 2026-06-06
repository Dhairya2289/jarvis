"""Audio recording via PipeWire pw-record."""

import subprocess


def record_audio(duration: int = 5, output_path: str = "/tmp/jarvis_voice.wav") -> str:
    """Record audio from default mic via pw-record.

    Uses PipeWire's pw-record with: --format=s16 --rate=16000 --channels=1
    Waits for process to complete or timeout.
    Returns the output_path if successful.
    Raises RuntimeError on failure.
    """
    cmd = [
        "pw-record",
        "--format=s16",
        "--rate=16000",
        "--channels=1",
        output_path,
    ]
    try:
        result = subprocess.run(
            cmd,
            timeout=duration + 3,
            capture_output=True,
            text=True,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"pw-record timed out after {duration + 3}s"
        ) from exc
    except FileNotFoundError as exc:
        raise RuntimeError(
            "pw-record not found. Please install PipeWire."
        ) from exc

    if result.returncode != 0:
        err = result.stderr.strip() or "unknown error"
        raise RuntimeError(f"pw-record failed (exit {result.returncode}): {err}")

    return output_path
