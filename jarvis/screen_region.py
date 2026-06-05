"""
JARVIS V3 — Screen Region Capture
──────────────────────────────────────────────────────────────
Capture full screen or a rectangular region.
Uses mss (cross-platform) with grim fallback for Wayland/Hyprland.
Returns a PIL Image.
"""

import base64
import io
import subprocess
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image


def capture_full() -> Image.Image:
    """Capture the entire screen and return a PIL Image."""
    try:
        import mss
        with mss.mss() as sct:
            monitor = sct.monitors[0]  # all monitors combined
            img = sct.grab(monitor)
            raw = mss.tools.to_png(img.rgb, img.size)
            return Image.open(BytesIO(raw)).convert("RGB")
    except Exception:
        pass

    # Fallback: grim (Wayland)
    try:
        tmp = Path.home() / ".jarvis" / "tmp_full.png"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["grim", str(tmp)], capture_output=True, timeout=5)
        if tmp.exists():
            return Image.open(tmp).convert("RGB")
    except Exception:
        pass

    raise RuntimeError("Cannot capture screen: mss and grim both failed")


def capture_region(
    left: int = 0, top: int = 0, width: int = 0, height: int = 0
) -> Image.Image:
    """Capture a rectangular region. If w/h are 0, captures full screen."""
    if width <= 0 or height <= 0:
        return capture_full()

    try:
        import mss
        with mss.mss() as sct:
            region = {"left": left, "top": top, "width": width, "height": height}
            img = sct.grab(region)
            raw = mss.tools.to_png(img.rgb, img.size)
            return Image.open(BytesIO(raw)).convert("RGB")
    except Exception:
        pass

    # Fallback: grim with region (slurp for selection, or direct coords)
    try:
        tmp = Path.home() / ".jarvis" / "tmp_region.png"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        # grim supports geometry: grim -g "x,y wxh" file
        geom = f"{left},{top} {width}x{height}"
        subprocess.run(["grim", "-g", geom, str(tmp)], capture_output=True, timeout=5)
        if tmp.exists():
            return Image.open(tmp).convert("RGB")
    except Exception:
        pass

    raise RuntimeError("Cannot capture region: mss and grim both failed")


def image_to_base64(img: Image.Image, fmt: str = "PNG") -> str:
    """Encode a PIL Image to base64 data URI."""
    buf = BytesIO()
    img.save(buf, format=fmt)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/{fmt.lower()};base64,{b64}"


def base64_to_image(b64: str) -> Image.Image:
    """Decode a base64 data URI to PIL Image."""
    if "," in b64:
        b64 = b64.split(",", 1)[1]
    raw = base64.b64decode(b64)
    return Image.open(BytesIO(raw))
