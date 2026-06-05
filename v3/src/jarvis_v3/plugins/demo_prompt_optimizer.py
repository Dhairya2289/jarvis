#!/usr/bin/env python3
"""Demo: Prompt Optimizer plugin for JARVIS V3.

Usage:
    PYTHONPATH=src python3 -m jarvis_v3.plugins.demo_prompt_optimizer
"""
from __future__ import annotations

from jarvis_v3.plugins.prompt_optimizer_plugin import optimize, generate_variant


def main() -> None:
    task = "Write a Python function that reads a JSON file"
    initial = "Write a Python function to read a JSON file."
    print("✨ Prompt Optimizer Demo")
    print(f"Task: {task}")
    print(f"Initial prompt: {initial}")

    print("\n--- Optimization ---")
    result = optimize(task, initial, iterations=2)
    print(f"Best prompt:\n{result['best_prompt']}")
    print(f"Final score: {result['final_score']}")

    print("\n--- Variant Generation ---")
    for strategy in ("concise", "detailed"):
        variant = generate_variant(task, initial, strategy=strategy)
        print(f"[{strategy}] {variant[:200]}...")


if __name__ == "__main__":
    main()
