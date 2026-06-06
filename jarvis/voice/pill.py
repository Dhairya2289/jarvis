#!/usr/bin/env python3
"""Floating visualizer pill at bottom center of screen."""

import json
import math
import os
import random
import sys
import tkinter as tk

STATE_FILE = "/tmp/jarvis_pill_state.json"

WIDTH, HEIGHT = 480, 70
BAR_COUNT = 7
BAR_WIDTH = 8
BAR_SPACING = 24
BAR_REGION_WIDTH = (BAR_COUNT - 1) * BAR_SPACING + BAR_WIDTH
BAR_BASE_Y = HEIGHT - 15
BAR_MIN_H = 10
BAR_MAX_H = 55

# Colors
THEME_COLORS = {
    "recording": "#ff5252",
    "processing": "#ffab00",
    "speaking": "#00d4ff",
    "idle": "#00d4ff",
    "done": "#00d4ff",
}

BG_COLOR = "#020c18"


def read_state():
    """Read pill state from the state file."""
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"state": "idle", "text": "", "amplitude": 0.0}


def draw_rounded_rect(canvas, x1, y1, x2, y2, radius, fill, outline=""):
    """Draw a rounded rectangle on a Canvas using arcs and lines."""
    points = [
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, fill=fill, outline=outline)


def main():
    root = tk.Tk()
    root.title("JARVIS Voice")
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.9)

    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    x = (screen_w - WIDTH) // 2
    y = screen_h - HEIGHT - 40
    root.geometry(f"{WIDTH}x{HEIGHT}+{x}+{y}")

    canvas = tk.Canvas(root, width=WIDTH, height=HEIGHT, bg=BG_COLOR, highlightthickness=0)
    canvas.pack()

    # Pill body
    body_margin = 4
    pill_rect = draw_rounded_rect(
        canvas,
        body_margin,
        body_margin,
        WIDTH - body_margin,
        HEIGHT - body_margin,
        radius=16,
        fill="#0a1929",
        outline="",
    )

    # Pulsing dot
    dot_x = 18
    dot_y = HEIGHT // 2
    dot_radius = 5
    dot = canvas.create_oval(
        dot_x - dot_radius, dot_y - dot_radius,
        dot_x + dot_radius, dot_y + dot_radius,
        fill=THEME_COLORS["idle"], outline="",
    )

    # Bars
    bar_start_x = (WIDTH - BAR_REGION_WIDTH) // 2 - 40
    bars = []
    for i in range(BAR_COUNT):
        bx = bar_start_x + i * BAR_SPACING
        line = canvas.create_line(
            bx, BAR_BASE_Y,
            bx, BAR_BASE_Y - BAR_MIN_H,
            width=BAR_WIDTH,
            fill=THEME_COLORS["idle"],
            capstyle=tk.ROUND,
        )
        bars.append(line)

    # Text label
    text_id = canvas.create_text(
        WIDTH // 2 + 20,
        HEIGHT // 2,
        text="",
        fill=THEME_COLORS["idle"],
        font=("sans-serif", 12, "bold"),
        anchor="w",
    )

    # State
    state_data = read_state()
    current_state = state_data.get("state", "idle")
    bar_heights = [BAR_MIN_H + random.randint(0, 10) for _ in range(BAR_COUNT)]
    phase = 0.0
    dot_pulse = 0.0
    hide_after_id = None

    def update_bars(color):
        """Update all bar colors."""
        for line in bars:
            canvas.itemconfig(line, fill=color)
        canvas.itemconfig(dot, fill=color)
        canvas.itemconfig(text_id, fill=color)

    def set_visibility(visible: bool):
        nonlocal hide_after_id
        if visible:
            root.deiconify()
            if hide_after_id is not None:
                root.after_cancel(hide_after_id)
                hide_after_id = None
        else:
            root.withdraw()

    def animate():
        nonlocal state_data, current_state, phase, dot_pulse, hide_after_id

        # Read state every ~100ms (animate runs every 50ms, so read every 2 ticks)
        new_state_data = read_state()
        new_state = new_state_data.get("state", "idle")

        if new_state != current_state:
            current_state = new_state
            if current_state in ("idle", "done"):
                if current_state == "idle":
                    set_visibility(False)
                elif current_state == "done":
                    # show briefly then hide
                    def _hide():
                        set_visibility(False)
                        # also clear state file to idle
                        try:
                            with open(STATE_FILE, "w") as f:
                                json.dump({"state": "idle", "text": "", "amplitude": 0.0}, f)
                        except OSError:
                            pass
                    hide_after_id = root.after(3000, _hide)
            else:
                set_visibility(True)
            color = THEME_COLORS.get(current_state, THEME_COLORS["idle"])
            update_bars(color)

        state_data = new_state_data
        text = state_data.get("text", "")
        amplitude = state_data.get("amplitude", 0.0)
        color = THEME_COLORS.get(current_state, THEME_COLORS["idle"])

        if current_state == "recording":
            # amplitude-driven jitter
            for i in range(BAR_COUNT):
                target = BAR_MIN_H + int((BAR_MAX_H - BAR_MIN_H) * amplitude)
                target += random.randint(-5, 5)
                target = max(BAR_MIN_H, min(BAR_MAX_H, target))
                bar_heights[i] += (target - bar_heights[i]) * 0.3
                bar_heights[i] = max(BAR_MIN_H, min(BAR_MAX_H, bar_heights[i]))

        elif current_state == "processing":
            # wave pattern
            for i in range(BAR_COUNT):
                wave = math.sin(phase + i * 0.8) * 0.5 + 0.5
                target = BAR_MIN_H + wave * (BAR_MAX_H - BAR_MIN_H)
                bar_heights[i] = target

        elif current_state == "speaking":
            # gentle pulse
            pulse = math.sin(phase * 2) * 0.3 + 0.7
            for i in range(BAR_COUNT):
                target = BAR_MIN_H + pulse * (BAR_MAX_H - BAR_MIN_H) * 0.6
                bar_heights[i] += (target - bar_heights[i]) * 0.1
                bar_heights[i] = max(BAR_MIN_H, min(BAR_MAX_H, bar_heights[i]))

        # Update canvas bars
        for i, line in enumerate(bars):
            bx = bar_start_x + i * BAR_SPACING
            h = bar_heights[i]
            canvas.coords(line, bx, BAR_BASE_Y, bx, BAR_BASE_Y - h)

        # Update dot pulse
        dot_pulse += 0.15
        dot_scale = 0.8 + 0.2 * abs(math.sin(dot_pulse))
        dr = int(dot_radius * dot_scale)
        canvas.coords(
            dot,
            dot_x - dr, dot_y - dr,
            dot_x + dr, dot_y + dr,
        )

        # Update text
        canvas.itemconfig(text_id, text=text)

        phase += 0.1
        root.after(50, animate)

    # Start hidden
    root.withdraw()
    root.after(50, animate)
    root.mainloop()


if __name__ == "__main__":
    main()
