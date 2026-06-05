"""
Context Engine — JARVIS V3 Intent Classifier
─────────────────────────────────────────────
Routes user queries to the correct specialist module using
keyword-based heuristics.  No LLM required at this stage.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Final

_LOG = logging.getLogger(__name__)

# ── Public Types ──────────────────────────────────────────

@dataclass
class Intent:
    """Represents a classified user intent."""
    category: str   # "logic" | "creative" | "vision" | "code" | "memory" | "system" | "chat"
    confidence: float
    specialist: str  # module name to route to


# ── Constants ─────────────────────────────────────────────

CATEGORY_SPECIALISTS: Final[dict[str, str]] = {
    "logic":    "orchestrator",
    "creative": "agent",
    "vision":   "vision_agent",
    "code":     "agent",
    "memory":   "episodic_memory",
    "system":   "tools",
    "chat":     "agent",
}

KEYWORDS: Final[dict[str, tuple[str, ...]]] = {
    "logic": (
        "calculate", "math", "reason", "logic", "compare", "analyze data",
        "deduce", "infer", "solve", "evaluate",
    ),
    "creative": (
        "write", "story", "poem", "brainstorm", "imagine", "design",
        "creative", "compose", "draft", "ideate",
    ),
    "vision": (
        "image", "see", "picture", "look", "screenshot", "visual", "photo",
        "describe image", "ocr", "eyes",
    ),
    "code": (
        "code", "program", "script", "python", "function", "debug",
        "refactor", "api", "class", "implement",
    ),
    "memory": (
        "remember", "recall", "what did I say", "past", "history",
        "previous", "earlier", "yesterday", "last time", "forget",
    ),
    "system": (
        "system", "health", "cpu", "disk", "process", "kill",
        "restart", "settings", "config", "update",
    ),
}

# Minimum confidence threshold for fallback to chat
_CONFIDENCE_FALLBACK_THRESHOLD: Final[float] = 0.2


# ── Core Functions ────────────────────────────────────────

def classify_intent(query: str) -> Intent:
    """
    Classify a user query into an Intent using keyword heuristics.

    Each keyword that matches in the query increments that category's score.
    Confidence = (best category score) / (total keywords matched).
    Falls back to "chat" / "agent" when confidence < 0.2 or no keywords match.
    """
    if not query or not query.strip():
        return Intent(category="chat", confidence=0.0, specialist="agent")

    query_lower = query.lower()
    # Tokenise: treat multi-word phrases as single tokens
    scores: dict[str, int] = {}
    total_matched = 0

    for category, keywords in KEYWORDS.items():
        category_score = 0
        for keyword in keywords:
            # Use word-boundary matching for single words; phrase match for multi-word
            if " " in keyword:
                if keyword in query_lower:
                    category_score += 1
                    total_matched += 1
            else:
                if re.search(r'\b' + re.escape(keyword) + r'\b', query_lower):
                    category_score += 1
                    total_matched += 1
        if category_score > 0:
            scores[category] = category_score

    # No matches → default to chat
    if not scores:
        return Intent(category="chat", confidence=0.0, specialist="agent")

    best_category = max(scores, key=lambda c: scores[c])
    best_score = scores[best_category]

    # Confidence: best score relative to total matches; cap at 1.0
    confidence = best_score / total_matched if total_matched > 0 else 0.0
    confidence = min(confidence, 1.0)

    # Fallback if confidence is too low
    if confidence < _CONFIDENCE_FALLBACK_THRESHOLD:
        return Intent(category="chat", confidence=confidence, specialist="agent")

    specialist = CATEGORY_SPECIALISTS[best_category]
    _LOG.debug(
        "classify_intent(%r) → category=%r specialist=%r confidence=%.2f",
        query, best_category, specialist, confidence,
    )
    return Intent(category=best_category, confidence=confidence, specialist=specialist)


def route(intent: Intent) -> str:
    """
    Return the specialist module name for the given Intent.

    This is a simple lookup; the caller is responsible for loading
    or dispatching to the named specialist.
    """
    return intent.specialist