#!/usr/bin/env python3
"""Minimal agent test CLI. The richer interface lives in jarvis_cli.py."""
from __future__ import annotations

import sys

from jarvis.agent import run_agent


def main() -> None:
    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
        print(f"\n[TASK] {task}\n" + "-" * 50)
        result = run_agent(task, status_callback=lambda m: print(f"  {m}"), session_id="test")
        print(f"\n[RESULT]\n{result}")
        return

    print("Jarvis test CLI - type tasks, Ctrl+C to quit\n")
    while True:
        try:
            task = input("> ").strip()
            if not task:
                continue
            result = run_agent(task, status_callback=lambda m: print(f"  {m}"), session_id="test")
            print(f"\n{result}\n" + "-" * 50)
        except KeyboardInterrupt:
            print("\nBye.")
            return


if __name__ == "__main__":
    main()
