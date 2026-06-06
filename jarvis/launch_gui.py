"""Launch the Jarvis HUD in a fullscreen native webview when pywebview is installed."""
from __future__ import annotations

import subprocess
import time


def launch_gui() -> None:
    try:
        import webview
    except Exception as e:
        raise SystemExit(f"pywebview is not installed: {e}")

    try:
        subprocess.run(["hyprctl", "dispatch", "workspace", "empty"], check=False, timeout=15)
    except subprocess.TimeoutExpired:
        pass  # Hyprland may be frozen, continue anyway
    time.sleep(0.5)
    webview.create_window(
        "JARVIS Master Console",
        "http://127.0.0.1:5050/static/dashboard.html",
        fullscreen=True,
        background_color="#020c18",
    )
    webview.start()


if __name__ == "__main__":
    launch_gui()
