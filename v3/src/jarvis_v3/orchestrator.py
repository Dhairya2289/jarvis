"""
JARVIS V3 Orchestrator — Experience-Based Model Routing
─────────────────────────────────────────────────────────
Learns which model works best for YOUR specific tasks over time.
Tracks success rates per (model × task_type) and routes accordingly.
Falls back to keyword heuristics on cold start.
"""

import json
from pathlib import Path
from typing import Dict

from jarvis_v3.config import MODELS, ROUTING_LOG

# ── Keyword classifiers ───────────────────────────────────

_CODE_KW = {
    "write code", "script", "implement", "function", "debug", "fix bug",
    "refactor", "class", "python", "bash", "compile", "syntax",
}
_RESEARCH_KW = {
    "research", "explain", "what is", "how does", "compare", "summarize",
    "find info", "look up", "search", "latest", "news", "recent",
}
_VISION_KW = {
    "screenshot", "image", "photo", "look at", "screen", "what do you see",
    "describe", "picture", "ui", "click", "visual",
}
_LOGIC_KW = {
    "plan", "design", "architect", "strategy", "decide", "analyze", "solve",
    "optimize", "prove", "theorem", "reason", "think through",
}
_SPEED_KW = {
    "quick", "fast", "brief", "short", "tl;dr", "tldr", "simple", "just", "one word",
}
_DEBATE_KW = {
    "should i", "is it better", "compare", "which is best", "recommend",
    "advise", "decide", "best way", "optimal", "versus", "vs", "pros and cons",
    "worth it", "or should",
}


def classify_task(task: str) -> str:
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


# ── Experience-based routing ──────────────────────────────


def _load_stats() -> Dict:
    try:
        return json.loads(Path(ROUTING_LOG).read_text())
    except Exception:
        return {}


def _save_stats(stats: Dict):
    try:
        Path(ROUTING_LOG).write_text(json.dumps(stats, indent=2))
    except Exception:
        pass


def get_best_model(task: str) -> str:
    """
    1. Check routing stats for best performing model for this task type.
    2. Fall back to tier list if insufficient data (<10 samples).
    3. Override to logic tier if high-risk keywords detected.
    """
    # Safety override — always use high-IQ for risky tasks
    risk_words = ["deploy", "delete", "rm", "format", "install", "sudo", "production"]
    if any(w in task.lower() for w in risk_words):
        return MODELS["logic"][0]

    task_type = classify_task(task)
    stats = _load_stats()
    tier = stats.get(task_type, {})

    # Find model with best success rate (min 5 samples)
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
        return best_model

    # Cold start: use tier defaults
    return MODELS.get(task_type, MODELS["logic"])[0]


def record_outcome(task_type: str, model: str, success: bool):
    """Call after each task to update routing statistics."""
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
