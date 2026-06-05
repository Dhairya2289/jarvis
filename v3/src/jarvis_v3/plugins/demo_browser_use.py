#!/usr/bin/env python3
"""Demo: browser-use plugin for JARVIS V3.

Usage:
    PYTHONPATH=src python3 -m jarvis_v3.plugins.demo_browser_use "Go to example.com and read the title"
"""
from __future__ import annotations

import asyncio
import sys

from jarvis_v3.plugins.browser_use_plugin import browse


def main() -> None:
    task = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Go to example.com and summarize the page"
    print("🌐 Browser-Use Demo")
    print(f"Task: {task}")
    result = asyncio.run(browse(task, headless=True))
    print(f"Result:\n{result}")


if __name__ == "__main__":
    main()
