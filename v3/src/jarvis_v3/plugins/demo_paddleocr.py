#!/usr/bin/env python3
"""Demo: PaddleOCR plugin for JARVIS V3.

Usage:
    PYTHONPATH=src python3 -m jarvis_v3.plugins.demo_paddleocr /path/to/image.png
"""
from __future__ import annotations

import sys

from jarvis_v3.plugins.paddleocr_plugin import extract_text


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "/home/dhairya/Pictures/Jarvis/vision_temp.png"
    print("🔍 PaddleOCR Demo")
    print(f"Image: {path}")
    text = extract_text(path)
    print(f"Extracted text:\n{text}")


if __name__ == "__main__":
    main()
