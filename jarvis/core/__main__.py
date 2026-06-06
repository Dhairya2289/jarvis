"""
JARVIS Core Loop CLI Entry Point
─────────────────────────────────
Run with:
    python -m jarvis.core
    python -m jarvis.core --loop

Or add --loop to the main jarvis cli (see --loop flag in jarvis/cli.py).
"""

import argparse
import asyncio
import sys


async def interactive_loop():
    """Read-eval-print loop driven by JARVISLoop.run_once."""
    from jarvis.core.loop import JARVISLoop

    print("JARVIS Unified Loop v3.0 — initialized")
    print("  Type 'exit' or 'quit' to stop.\n")

    async with JARVISLoop() as loop:
        while True:
            try:
                user_input = input("JARVIS> ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nGoodbye.")
                break

            if not user_input:
                continue

            if user_input.lower() in ("exit", "quit"):
                print("Session ended.")
                break

            try:
                response = await loop.run_once(user_input, source="cli")
                print(f"\n{response}\n")
            except Exception as exc:
                print(f"[ERROR] {exc}\n")


def main():
    parser = argparse.ArgumentParser(description="JARVIS Core Loop CLI")
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Start the interactive unified loop (default when run as module)",
    )
    parser.add_argument(
        "task",
        nargs="*",
        help="One-shot task — runs the loop once and exits",
    )
    args = parser.parse_args()

    if args.task or args.loop:
        # One-shot or --loop flag
        task_text = " ".join(args.task) if args.task else ""

        async def run_one():
            async with JARVISLoop() as loop:
                result = await loop.run_once(task_text, source="cli")
                print(result)

        asyncio.run(run_one())
        return

    # Default: run interactive loop
    asyncio.run(interactive_loop())


if __name__ == "__main__":
    main()