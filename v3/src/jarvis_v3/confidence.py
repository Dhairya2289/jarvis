"""JARVIS Confidence Engine

Scores confidence before committing to a response.
Routes to research/debate/clarification based on score.
"""
from __future__ import annotations

import logging
import re
from typing import Final

import anthropic

from jarvis_v3.config import (
    CONFIDENCE_ASK_BELOW,
    CONFIDENCE_RESEARCH_BELOW,
    FCC_AUTH_TOKEN,
    FCC_BASE_URL,
    MODELS,
)

_log = logging.getLogger(__name__)

_client: anthropic.Anthropic | None = None


def _anthropic_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(
            base_url=FCC_BASE_URL, api_key=FCC_AUTH_TOKEN or "freecc"
        )
    return _client


def score(task: str, response: str) -> float:
    """Ask a speed model to rate confidence. Returns 0.0–1.0.

    Falls back to 0.7 when scoring itself fails.
    """
    prompt = (
        "Rate your confidence that this response fully and correctly "
        "answers the task.\n"
        f"Task: {task}\n"
        f"Response summary: {response[:400]}\n\n"
        "Respond with ONLY a number from 0 to 10. "
        "10 = completely certain, 0 = guessing wildly."
    )
    try:
        r = _anthropic_client().messages.create(
            model=MODELS["speed"][0],
            max_tokens=5,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = r.content[0].text.strip()
        # Extract the first numeric sequence
        match = re.search(r"[\d.]+", raw)
        if not match:
            _log.warning("No numeric score found in model output: %s", raw)
            return 0.5
        val = float(match.group())
        return min(max(val / 10.0, 0.0), 1.0)
    except Exception as exc:
        _log.warning("Confidence scoring failed: %s", exc)
        return 0.7  # Assume OK if scoring fails


def should_research_more(task: str, response: str) -> bool:
    """Return True if confidence is below the research threshold."""
    return score(task, response) < CONFIDENCE_RESEARCH_BELOW


def should_ask_user(task: str, response: str) -> bool:
    """Return True if confidence is below the ask-user threshold."""
    return score(task, response) < CONFIDENCE_ASK_BELOW


__all__ = ["score", "should_research_more", "should_ask_user"]
