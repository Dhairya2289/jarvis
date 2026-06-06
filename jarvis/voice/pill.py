#!/usr/bin/env python3
"""Floating physics-based companion widget that follows the cursor."""

import json
import math
import subprocess
import tkinter as tk


STATE_FILE = "/tmp/jarvis_pill_state.json"

# Map legacy engine states to CursorPebble states
STATE_MAP = {
    "idle": "idle",
    "recording": "listening",
    "processing": "thinking",
    "speaking": "speaking",
    "done": "idle",
}


class CursorPebble:
    """Floating physics-based companion widget."""

    STATES = {
        "idle":      {"color": "#1a1a2e", "size": 40, "pulse": False},
        "listening": {"color": "#e94560", "size": 50, "pulse": True},
        "thinking":  {"color": "#f5a623", "size": 45, "pulse": True},
        "speaking":  {"color": "#00d2ff", "size": 45, "pulse": True},
        "working":   {"color": "#7fff7f", "size": 42, "pulse": True},
    }

    def __init__(self, master=None):
        if master is None:
            self.root = tk.Tk()
        else:
            self.root = master

        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.9)
        self.root.config(bg="#020c18")

        self.size = 50
        self.target_x = 0
        self.target_y = 0
        self.current_x = 0
        self.current_y = 0
        self.spring_k = 0.15
        self.friction = 0.8
        self.vx = 0
        self.vy = 0
        self.state = "idle"
        self.pulse_phase = 0.0
        self._amplitude = 0.0

        self.canvas = tk.Canvas(
            self.root, width=100, height=100,
            bg="#020c18", highlightthickness=0,
        )
        self.canvas.pack()
        self.oval = self.canvas.create_oval(0, 0, 0, 0, fill="#1a1a2e", outline="")

        self._read_cursor()
        self._update()
        self._check_state_file()

    def _read_cursor(self):
        """Get cursor position via xdotool or hyprctl."""
        try:
            if self._has_tool("xdotool"):
                result = subprocess.run(
                    ["xdotool", "getmouselocation"],
                    capture_output=True, text=True, timeout=0.5,
                )
                parts = result.stdout.strip().split()
                x = int(parts[0].split(":")[1])
                y = int(parts[1].split(":")[1])
            elif self._has_tool("hyprctl"):
                result = subprocess.run(
                    ["hyprctl", "cursorpos"],
                    capture_output=True, text=True, timeout=0.5,
                )
                x_str, y_str = result.stdout.strip().split(",")
                x = int(x_str.strip())
                y = int(y_str.strip())
            else:
                x = self.target_x or 100
                y = self.target_y or 100
            self.target_x = x
            self.target_y = y + 40  # float below cursor
        except Exception:
            if self.target_x == 0 and self.target_y == 0:
                screen_w = self.root.winfo_screenwidth()
                screen_h = self.root.winfo_screenheight()
                self.target_x = screen_w // 2
                self.target_y = screen_h // 2
        self.root.after(50, self._read_cursor)

    @staticmethod
    def _has_tool(name: str) -> bool:
        """Return True if the named executable is on PATH."""
        try:
            subprocess.run([name, "--version"],
                           capture_output=True, timeout=1)
            return True
        except Exception:
            return False

    def _update(self):
        """Spring physics: pebble follows cursor with lag."""
        ax = (self.target_x - self.current_x) * self.spring_k
        ay = (self.target_y - self.current_y) * self.spring_k
        self.vx = (self.vx + ax) * self.friction
        self.vy = (self.vy + ay) * self.friction
        self.current_x += self.vx
        self.current_y += self.vy

        cfg = self.STATES.get(self.state, self.STATES["idle"])
        size = cfg["size"]

        if cfg["pulse"]:
            self.pulse_phase += 0.1
            scale = 1.0 + 0.15 * math.sin(self.pulse_phase)
            size = int(size * scale)

        # Amplitude-driven extra jitter when listening
        if self.state == "listening" and self._amplitude > 0:
            size += int(self._amplitude * 10)

        x = self.current_x - size // 2
        y = self.current_y - size // 2
        self.root.geometry(f"{size}x{size}+{int(x)}+{int(y)}")
        self.canvas.coords(self.oval, 0, 0, size, size)
        self.canvas.itemconfig(self.oval, fill=cfg["color"])
        self.canvas.config(width=size, height=size)

        self.root.after(16, self._update)  # ~60 fps

    def _check_state_file(self):
        """Read STATE_FILE for external control."""
        try:
            with open(STATE_FILE) as f:
                data = json.load(f)
            raw_state = data.get("state", "idle")
            mapped = STATE_MAP.get(raw_state, raw_state)
            if mapped in self.STATES:
                self.state = mapped
            self._amplitude = data.get("amplitude", 0.0)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        self.root.after(100, self._check_state_file)

    def run(self):
        self.root.mainloop()


def main():
    pebble = CursorPebble()
    pebble.run()


if __name__ == "__main__":
    main()
