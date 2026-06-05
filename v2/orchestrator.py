"""JARVIS Orchestrator v2 — Experience-Based Model Routing

Learns which model works best for YOUR specific tasks over time.
Tracks success rates per (model × task_type) and routes accordingly.
Falls back to keyword heuristics on cold start.
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Final

from config import BRAIN_MODEL, FALLBACK_MODEL, MODELS, ROUTING_LOG

_log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
#  Keyword classifiers
# ═══════════════════════════════════════════════════════════
_CODE_KW: Final[frozenset[str]] = frozenset({
    "write code", "script", "implement", "function", "debug", "fix bug",
    "refactor", "class", "python", "bash", "compile", "syntax",
})
_RESEARCH_KW: Final[frozenset[str]] = frozenset({
    "research", "explain", "what is", "how does", "compare", "summarize",
    "find info", "look up", "search", "latest", "news", "recent",
})
_VISION_KW: Final[frozenset[str]] = frozenset({
    "screenshot", "image", "photo", "look at", "screen", "what do you see",
    "describe", "picture", "ui", "click", "visual",
})
_LOGIC_KW: Final[frozenset[str]] = frozenset({
    "plan", "design", "architect", "strategy", "decide", "analyze", "solve",
    "optimize", "prove", "theorem", "reason", "think through",
})
_SPEED_KW: Final[frozenset[str]] = frozenset({
    "quick", "fast", "brief", "short", "tl;dr", "tldr", "simple", "just", "one word",
})
_DEBATE_KW: Final[frozenset[str]] = frozenset({
    "should i", "better", "which", "recommend", "best way", "advise", "versus",
    "vs", "compare", "pros and cons", "worth it", "or should",
})


def classify_task(task: str) -> str:
    """Classify a task string into a routing category."""
    t = task.lower()
    if any(k in t for k in _VISION_KW):
        return "vision"
    if any(k in t for k in _CODE_KW):
        return "code"
    if any(k in t for k in _DEBATE_KW):
        return "debate"
    if any(k in t for k in _LOGIC_KW):
        return "logic"
    if any(k in t for k in _RESEARCH_KW):
        return "research"
    if any(k in t for k in _SPEED_KW):
        return "speed"
    return "logic"  # Default to high-intelligence


# ═══════════════════════════════════════════════════════════
#  Stats I/O
# ═══════════════════════════════════════════════════════════
def _load_stats() -> dict:
    try:
        if not ROUTING_LOG.exists():
            return {}
        return json.loads(ROUTING_LOG.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _log.warning("Corrupt routing stats: %s", exc)
        return {}
    except OSError as exc:
        _log.warning("Could not read routing stats: %s", exc)
        return {}


def _save_stats(stats: dict) -> None:
    try:
        ROUTING_LOG.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    except OSError as exc:
        _log.warning("Could not save routing stats: %s", exc)


# ═══════════════════════════════════════════════════════════
#  Public API
# ═════════════════════════════════════════════════════════==
def get_best_model(task: str) -> str:
    """Return the best model for *task* based on experience stats.

    1. Check routing stats for best performing model for this task type.
    2. Fall back to tier list if insufficient data (<5 samples).
    3. Override to logic tier if high-risk keywords detected.
    """
    risk_words = { "deploy", "delete", "rm", "format", "install", "sudo", "production" }
    if any(w in task.lower() for w in risk_words):
        _log.info("Risky task detected — routing to logic tier")
        return MODELS["logic"][0]

    task_type = classify_task(task)
    stats = _load_stats()
    tier = stats.get(task_type, {})

    best_model = None
    best_score = -1.0
    for model, data in tier.items():
        attempts = data.get("attempts", 0)
        if attempts >= 5:
            success_rate = data.get("successes", 0) / attempts
            adjusted = success_rate * (1 - 1 / (attempts + 1))
            if adjusted > best_score:
                best_score = adjusted
                best_model = model

    if best_model:
        _log.debug("Routing %s → %s (score=%.2f)", task_type, best_model, best_score)
        return best_model

    # Cold start
    default = MODELS.get(task_type, MODELS["logic"])[0]
    _log.debug("Cold-start routing %s → %s", task_type, default)
    return default


def record_outcome(task_type: str, model: str, success: bool) -> None:
    """Update routing statistics after a task completes."""
    stats = _load_stats()
    stats.setdefault(task_type, {}).setdefault(
        model, {"attempts": 0, "successes": 0}
    )
    stats[task_type][model]["attempts"] += 1
    if success:
        stats[task_type][model]["successes"] += 1
    _save_stats(stats)


def get_routing_report() -> str:
    """Human-readable summary of routing stats."""
    stats = _load_stats()
    if not stats:
        return "No routing data yet. Run more tasks to build experience."
    lines = ["📊 *Routing Intelligence Report*\n"]
    for task_type, models in stats.items():
        lines.append(f"**{task_type.upper()}**")
        for model, data in sorted(
            models.items(),
            key=lambda x: x[1].get("successes", 0) / max(x[1].get("attempts", 1), 1),
            reverse=True,
        ):
            a = data.get("attempts", 0)
            s = data.get("successes", 0)
            rate = f"{s / a * 100:.0f}%" if a else "N/A"
            short = model.split("/")[-1][:25]
            lines.append(f"  `{short}`: {rate} ({s}/{a})")
        lines.append("")
    return "\n".join(lines)


__all__ = [
    "classify_task",
    "get_best_model",
    "record_outcome",
    "get_routing_report",
]
