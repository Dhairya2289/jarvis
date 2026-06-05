"""
JARVIS V3 — Fast-Path Local Router
──────────────────────────────────────────────────────────────
Intercept common OS / Hyprland commands and execute them
instantly without calling the LLM. Reduces latency for
simple everyday actions from ~2s to ~50ms.
"""

import re
import subprocess

from jarvis_v3.tools import _os_hardware_control, _os_process_control

# ── Command patterns ──────────────────────────────────────

_VOL_PATTERNS = [
    (r"^(turn\s+)?(the\s+)?volume\s+(up|higher|increase)$", "volume_up"),
    (r"^(turn\s+)?(the\s+)?volume\s+(down|lower|decrease)$", "volume_down"),
    (r"^(mute|unmute|toggle\s+mute)$", "mute_toggle"),
]

_BRIGHTNESS_PATTERNS = [
    (r"^(increase|raise|turn\s+up)\s+(the\s+)?brightness$", "brightness_up"),
    (r"^(decrease|lower|turn\s+down)\s+(the\s+)?brightness$", "brightness_down"),
]

_LOCK_PATTERNS = [
    (r"^(lock\s+screen|lock\s+pc|lock)\s*$", "lock"),
]

_SUSPEND_PATTERNS = [
    (r"^(suspend|sleep|put\s+to\s+sleep)\s*$", "suspend"),
]

_WIFI_PATTERNS = [
    (r"^(turn\s+)?(the\s+)?wi-?fi\s+(on|enable)$", "wifi_on"),
    (r"^(turn\s+)?(the\s+)?wi-?fi\s+(off|disable)$", "wifi_off"),
]

_BT_PATTERNS = [
    (r"^(turn\s+)?(the\s+)?bluetooth\s+(on|enable)$", "bluetooth_on"),
    (r"^(turn\s+)?(the\s+)?bluetooth\s+(off|disable)$", "bluetooth_off"),
]

_APP_PATTERNS = [
    (r"^open\s+(.+)$", lambda m: _os_process_control("launch", m.group(1))),
    (r"^launch\s+(.+)$", lambda m: _os_process_control("launch", m.group(1))),
    (r"^close\s+(.+)$", lambda m: _os_process_control("kill", m.group(1))),
    (r"^kill\s+(.+)$", lambda m: _os_process_control("kill", m.group(1))),
]

_ALL_PATTERNS = [
    *[(p, a) for p, a in _VOL_PATTERNS],
    *[(p, a) for p, a in _BRIGHTNESS_PATTERNS],
    *[(p, a) for p, a in _LOCK_PATTERNS],
    *[(p, a) for p, a in _SUSPEND_PATTERNS],
    *[(p, a) for p, a in _WIFI_PATTERNS],
    *[(p, a) for p, a in _BT_PATTERNS],
    *_APP_PATTERNS,
]


def execute_fast_path(task: str) -> str:
    """
    Try to execute task locally without LLM.
    Returns empty string if no fast-path matched.
    """
    t = task.strip().lower()

    for pattern, action in _ALL_PATTERNS:
        m = re.match(pattern, t, re.IGNORECASE)
        if m:
            if callable(action):
                return action(m)
            return _os_hardware_control(action)

    # Hyprland workspace switching
    ws_match = re.match(r"^(go to |switch to )?workspace\s+(\d+)$", t, re.IGNORECASE)
    if ws_match:
        ws = ws_match.group(2)
        subprocess.run(["hyprctl", "dispatch", "workspace", ws], capture_output=True)
        return f"Switched to workspace {ws}"

    # Hyprland window focus
    win_match = re.match(r"^(focus|switch to)\s+(.+)$", t, re.IGNORECASE)
    if win_match:
        cls = win_match.group(2).strip()
        subprocess.run(["hyprctl", "dispatch", "focuswindow", f"class:{cls}"], capture_output=True)
        return f"Focused window: {cls}"

    return ""
