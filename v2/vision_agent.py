"""JARVIS Vision Agent — Computer Use

Processes screenshots with vision models to find UI coordinates.
"""
from __future__ import annotations

import base64
import json
import logging
import subprocess
from pathlib import Path

from api_manager import call_with_rotation
from config import FCC_AUTH_TOKEN, FCC_BASE_URL

_log = logging.getLogger(__name__)


def _res_from_hyprctl() -> tuple[int, int]:
    """Return (width, height) of primary monitor via hyprctl."""
    try:
        raw = subprocess.run(
            ["hyprctl", "monitors", "-j"],
            capture_output=True,
            text=True,
        ).stdout
        monitors = json.loads(raw)
        if monitors:
            return int(monitors[0]["width"]), int(monitors[0]["height"])
    except Exception:
        _log.debug("Could not query monitor resolution")
    return 1920, 1080


def get_element_coordinates(
    element_desc: str, screenshot_path: str
) -> dict[str, Any]:
    """Ask a vision model to find coordinates for *element_desc*.

    Returns ``{"x": int, "y": int}`` in pixel space or
    ``{"error": str}`` on failure.
    """
    try:
        img_bytes = Path(screenshot_path).read_bytes()
        img_data = base64.b64encode(img_bytes).decode()
    except OSError as exc:
        return {"error": f"Screenshot read failed: {exc}"}

    prompt = (
        "You are a computer-use assistant. Locate the following element on the "
        f"screen: '{element_desc}'. Return ONLY a JSON object with 'x' and 'y' "
        "coordinates as percentages (0–100) of the width/height. "
        'Format: {"x": 50, "y": 50}. '
        'If not found, return {"error": "not_found"}.'
    )

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": img_data,
                    },
                },
                {"type": "text", "text": prompt},
            ],
        }
    ]

    try:
        response = call_with_rotation(
            task=f"Locate {element_desc}",
            task_type="vision",
            messages=messages,
            system="You are a precise vision coordinate extractor.",
        )
    except Exception as exc:
        _log.error("Vision API call failed: %s", exc, exc_info=True)
        return {"error": str(exc)}

    text = ""
    if hasattr(response, "content"):
        for block in response.content:
            if hasattr(block, "type") and block.type == "text" and hasattr(block, "text"):
                text += block.text
    else:
        text = str(response)

    if "{" in text and "}" in text:
        try:
            data = json.loads(text[text.find("{") : text.rfind("}") + 1])
            return data
        except json.JSONDecodeError:
            _log.warning("Vision model returned invalid JSON: %s", text[:200])
    return {"error": f"Invalid model response format: {text[:100]}"}


def execute_vision_click(element_desc: str) -> str:
    """Full loop: screenshot → find → click."""
    from tools import execute_human_input, execute_screenshot

    path = execute_screenshot("vision_temp.png")
    if path.startswith("[ERROR]"):
        return path

    coords = get_element_coordinates(element_desc, path)
    if "error" in coords:
        return f"[ERROR] Vision failed: {coords['error']}"

    w, h = _res_from_hyprctl()
    px = int((coords["x"] / 100) * w)
    py = int((coords["y"] / 100) * h)
    return execute_human_input("click", f"{px} {py}")


__all__ = ["get_element_coordinates", "execute_vision_click"]
