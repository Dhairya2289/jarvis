"""Prompt Optimizer plugin for JARVIS V3.

Python adaptation of the prompt-optimizer TypeScript project.
Iteratively improves a prompt using LLM critique and A/B variant testing.
"""
from __future__ import annotations

import logging
import random
import time
from typing import Any

_log = logging.getLogger(__name__)


def _critique_prompt(task: str, prompt: str) -> str:
    """Ask the LLM to critique the prompt for the given task.

    Returns a short critique string (strengths + weaknesses).
    """
    try:
        from jarvis_v3.api_manager import call_with_rotation
        system = (
            "You are a prompt-engineering expert. "
            "Review the prompt below for the given task. "
            "Return ONLY a short critique (max 150 words): "
            "list 1 strength and 2 concrete weaknesses."
        )
        user = f"Task: {task}\n\nPrompt:\n{prompt}"
        response = call_with_rotation(
            task="prompt critique",
            task_type="logic",
            messages=[{"role": "user", "content": user}],
            system=system,
            max_tokens=300,
        )
        if hasattr(response, "content"):
            return response.content[0].text.strip()
        return str(response).strip()
    except Exception as exc:
        _log.error("Critique failed: %s", exc)
        return "Critique unavailable."


def _rewrite_prompt(task: str, prompt: str, critique: str) -> str:
    """Ask the LLM to rewrite the prompt incorporating the critique."""
    try:
        from jarvis_v3.api_manager import call_with_rotation
        system = (
            "You are a prompt-engineering expert. "
            "Rewrite the prompt to fix the weaknesses listed in the critique. "
            "Return ONLY the rewritten prompt, nothing else."
        )
        user = (
            f"Task: {task}\n\n"
            f"Original Prompt:\n{prompt}\n\n"
            f"Critique:\n{critique}\n\n"
            "Rewrite the prompt:"
        )
        response = call_with_rotation(
            task="prompt rewrite",
            task_type="logic",
            messages=[{"role": "user", "content": user}],
            system=system,
            max_tokens=500,
        )
        if hasattr(response, "content"):
            return response.content[0].text.strip()
        return str(response).strip()
    except Exception as exc:
        _log.error("Rewrite failed: %s", exc)
        return prompt


def optimize(
    task: str,
    initial_prompt: str,
    *,
    iterations: int = 3,
) -> dict[str, Any]:
    """Iteratively optimize a prompt for a given task.

    Args:
        task: The task description.
        initial_prompt: Starting prompt.
        iterations: Number of critique → rewrite cycles.

    Returns:
        Dict with 'best_prompt', 'history', and 'final_score'.
    """
    current = initial_prompt
    history: list[dict[str, str]] = []
    for i in range(iterations):
        _log.info("Optimization iteration %d/%d", i + 1, iterations)
        critique = _critique_prompt(task, current)
        new_prompt = _rewrite_prompt(task, current, critique)
        history.append({
            "iteration": str(i + 1),
            "prompt": new_prompt,
            "critique": critique,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        current = new_prompt

    # Simple heuristic score (longer + more specific = better, capped)
    score = min(len(current.split()) / 50.0, 1.0)
    _log.info("Optimization complete. Final score: %.2f", score)
    return {
        "best_prompt": current,
        "initial_prompt": initial_prompt,
        "history": history,
        "final_score": round(score, 2),
    }


def generate_variant(task: str, base_prompt: str, strategy: str = "concise") -> str:
    """Generate a single variant of *base_prompt* using *strategy*.

    Strategies:
        concise   — shorter, punchier
        detailed  — more context and examples
        creative  — more expressive, open-ended
    """
    try:
        from jarvis_v3.api_manager import call_with_rotation
        system = (
            f"You are a prompt-engineering expert. "
            f"Create a {strategy} variant of the user's prompt. "
            f"Return ONLY the variant prompt, nothing else."
        )
        response = call_with_rotation(
            task=f"prompt variant {strategy}",
            task_type="logic",
            messages=[{"role": "user", "content": base_prompt}],
            system=system,
            max_tokens=500,
        )
        if hasattr(response, "content"):
            return response.content[0].text.strip()
        return str(response).strip()
    except Exception as exc:
        _log.error("Variant generation failed: %s", exc)
        return base_prompt


__all__ = ["optimize", "generate_variant"]
