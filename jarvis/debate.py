"""JARVIS Debate Engine — Multi-Model Consensus Protocol (V3 async wrapper)."""
from __future__ import annotations

import logging
from jarvis.compat.bridge import to_async

_log = logging.getLogger(__name__)

# ── Inline V2 debate logic (sync) ─────────────────────────
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Final

import anthropic

from jarvis.config import (
    BRAIN_MODEL,
    DEBATE_LOG,
    DEBATE_ROUNDS,
    DEBATE_TRIGGER_WORDS,
    FCC_AUTH_TOKEN,
    FCC_BASE_URL,
    MODELS,
)

_DEBATE_MODELS: Final[dict[str, str]] = {
    "DeepSeek R1": MODELS["debate"][0],
    "Llama 3.3 70B": MODELS["debate"][1],
    "Llama 3.1 405B": MODELS["debate"][2],
}

_client = anthropic.Anthropic(base_url=FCC_BASE_URL, api_key=FCC_AUTH_TOKEN or "freecc")


def _query(model: str, prompt: str, max_tokens: int = 1500) -> str:
    try:
        r = _client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return r.content[0].text.strip()
    except Exception as exc:
        _log.error("Debate query failed: %s", exc)
        return f"[ERROR] {exc}"


def _query_parallel(prompts: dict[str, tuple[str, str, str]]) -> dict[str, str]:
    results: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(_query, model, prompt, 1500): name
            for name, (model, prompt, _system) in prompts.items()
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception as exc:
                _log.error("Debate future %s failed: %s", name, exc)
                results[name] = f"[ERROR] {exc}"
    return results


def _run_debate_sync(question: str, context: str = "") -> str:
    start = time.time()
    full_q = f"{context}\n\n{question}" if context else question
    _log.info("Starting %d-model debate…", len(_DEBATE_MODELS))

    # Round 1
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

    # Round 2
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

    # Synthesis
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


async def run_debate(question: str, context: str = "") -> str:
    """Async wrapper around the sync V2 debate engine."""
    return await to_async(_run_debate_sync)(question, context)


__all__ = ["run_debate"]
