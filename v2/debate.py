"""JARVIS Debate Engine — Multi-Model Consensus Protocol

For complex decisions, 3 high-IQ models debate in 2 rounds,
then the Brain synthesizes the consensus.

Round 1: Independent positions
Round 2: Each model critiques the others + revises
Synthesis: Brain model produces final answer from the transcript
"""
from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Final

import anthropic

from config import (
    BRAIN_MODEL,
    DEBATE_LOG,
    DEBATE_ROUNDS,
    DEBATE_TRIGGER_WORDS,
    FCC_AUTH_TOKEN,
    FCC_BASE_URL,
    MODELS,
)

_log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
#  Anthropic client
# ═══════════════════════════════════════════════════════════
_client: anthropic.Anthropic | None = None


def _anthropic_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(
            base_url=FCC_BASE_URL, api_key=FCC_AUTH_TOKEN or "freecc"
        )
    return _client


# ═══════════════════════════════════════════════════════════
#  Model registry
# ═════════════════════════════════════════════════════════==
_DEBATE_MODELS: Final[dict[str, str]] = {
    "DeepSeek R1":    MODELS["debate"][0],
    "Gemini 2.5 Pro": MODELS["debate"][1],
    "Nemotron 120B":  MODELS["debate"][2],
}


# ═══════════════════════════════════════════════════════════
#  Query helpers
# ═════════════════════════════════════════════════════════==
def _query(
    model: str,
    prompt: str,
    *,
    system: str = "",
    max_tokens: int = 1200,
) -> str:
    try:
        msgs = [{"role": "user", "content": prompt}]
        kwargs: dict = {"model": model, "max_tokens": max_tokens, "messages": msgs}
        if system:
            kwargs["system"] = system
        r = _anthropic_client().messages.create(**kwargs)
        return r.content[0].text.strip() if r.content else "(no response)"
    except Exception as exc:
        _log.warning("Debate query failed for %s: %s", model, exc)
        return f"[ERROR] {exc}"


def _query_parallel(
    prompts: dict[str, tuple[str, str, str]]
) -> dict[str, str]:
    """Query multiple models in parallel.

    ``prompts`` maps name → (model, prompt, system).
    """
    results: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=len(prompts)) as pool:
        futures = {
            pool.submit(_query, model, prompt, system=system): name
            for name, (model, prompt, system) in prompts.items()
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception as exc:
                _log.error("Debate future %s failed: %s", name, exc)
                results[name] = f"[ERROR] {exc}"
    return results


# ═══════════════════════════════════════════════════════════
#  Debate rounds
# ═════════════════════════════════════════════════════════==
def run_debate(question: str, context: str = "") -> str:
    """Full debate protocol. Returns synthesized final answer.

    Also logs debate to ``~/.jarvis/debate_log.jsonl`` for review.
    """
    start = time.time()
    full_q = f"{context}\n\n{question}" if context else question
    _log.info("Starting %d-model debate…", len(_DEBATE_MODELS))

    # ── Round 1: Independent positions ────────────────────
    _log.info("Round 1: Independent positions")
    r1_prompts = {
        name: (
            model,
            full_q,
            f"You are {name}, an expert AI. Give your best, concise answer. "
            "Be direct. State your position and key reasoning. 200-300 words max.",
        )
        for name, model in _DEBATE_MODELS.items()
    }
    positions = _query_parallel(r1_prompts)

    # ── Round 2: Critique & Revise ─────────────────────────
    _log.info("Round 2: Cross-critique")
    r2_prompts: dict[str, tuple[str, str, str]] = {}
    for name, model in _DEBATE_MODELS.items():
        others = "\n\n".join(
            f"**{n}** said:\n{p}" for n, p in positions.items() if n != name
        )
        r2_prompts[name] = (
            model,
            f"Original question: {question}\n\n"
            f"You previously said:\n{positions[name]}\n\n"
            f"The other models said:\n{others}\n\n"
            "Now: (1) Identify the strongest point they made. "
            "(2) Identify the biggest mistake or gap in their reasoning. "
            "(3) Give your REVISED final answer incorporating the best insights. "
            "Be sharp. 200-300 words.",
            f"You are {name}, a critical AI debater.",
        )
    revisions = _query_parallel(r2_prompts)

    # ── Synthesis: Brain model ─────────────────────────────
    _log.info("Synthesis")
    debate_transcript = "\n\n---\n\n".join(
        f"**{name} — Round 1:**\n{positions[name]}\n\n"
        f"**{name} — Round 2 (revised):**\n{revisions.get(name, '')}"
        for name in _DEBATE_MODELS
    )

    synthesis_prompt = (
        "You are the Arbiter AI. Three expert models debated this question:\n\n"
        f"**Question:** {question}\n\n"
        f"**Full Debate Transcript:**\n{debate_transcript}\n\n"
        "Your task:\n"
        "1. Identify the consensus points all models agree on.\n"
        "2. For disagreements, state which position is strongest and why.\n"
        "3. Produce the DEFINITIVE final answer — clear, actionable, complete.\n"
        "This is the final word. Make it exceptional."
    )
    final_answer = _query(BRAIN_MODEL, synthesis_prompt, max_tokens=1500)

    # ── Log ───────────────────────────────────────────────
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "question": question,
        "positions": positions,
        "revisions": revisions,
        "final": final_answer,
        "duration_s": round(time.time() - start, 1),
    }
    try:
        with open(DEBATE_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        _log.warning("Could not append to debate log: %s", exc)

    _log.info("Debate complete in %.1fs", record["duration_s"])
    return final_answer


def should_debate(task: str) -> bool:
    """Heuristic: trigger debate on decision/comparison questions."""
    t = task.lower()
    return any(w in t for w in DEBATE_TRIGGER_WORDS)


def quick_debate(question: str) -> str:
    """Single-round fast debate (skip revision round for speed)."""
    r1_prompts = {
        name: (
            model,
            question,
            f"You are {name}. Answer concisely and precisely. 150 words max.",
        )
        for name, model in _DEBATE_MODELS.items()
    }
    positions = _query_parallel(r1_prompts)

    all_answers = "\n\n".join(f"**{n}:** {p}" for n, p in positions.items())
    synthesis = _query(
        BRAIN_MODEL,
        f"Question: {question}\n\nThree models answered:\n{all_answers}\n\n"
        "Synthesize the single best answer in 100-150 words.",
        max_tokens=500,
    )
    return synthesis


__all__ = ["run_debate", "should_debate", "quick_debate"]
