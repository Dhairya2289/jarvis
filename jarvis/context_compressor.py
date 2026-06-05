"""JARVIS Context Compressor

Summarises long conversation history to keep sessions manageable.
Ported and adapted from Hermes Agent (MIT License).
Original: hermes/agent/context_compressor.py + hermes/agent/context_engine.py
"""
from __future__ import annotations

import logging
from typing import Final

from jarvis.api_manager import call_with_rotation
from jarvis.config import MAX_TOKENS

_log = logging.getLogger(__name__)

# Rough token budget: 1 word ~ 0.75 tokens.  When the uncompressed context
# exceeds this word count, compression is triggered.
_COMPRESSION_WORD_THRESHOLD: Final[int] = 1200


def should_compress(messages: list[dict[str, str]]) -> bool:
    """Return True if the context is large enough to benefit from compression."""
    total_words = sum(len(m.get("content", "").split()) for m in messages)
    return total_words > _COMPRESSION_WORD_THRESHOLD


def compress(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """Compress *messages* by summarising early turns into a single system
    memory block, preserving the most recent turns verbatim.

    Args:
        messages: Raw conversation history (oldest first).

    Returns:
        Compressed history: a single ``{"role":"system","content":...}``
        memory block followed by the last few verbatim turns.
    """
    if not messages:
        return messages
    if not should_compress(messages):
        return messages

    # Keep the most recent 6 turns verbatim; summarise everything before.
    verbatim_cut = max(1, len(messages) - 6)
    to_summarise = messages[:verbatim_cut]
    verbatim = messages[verbatim_cut:]

    transcript = "\n\n".join(
        f"[{m['role'].upper()}] {m.get('content', '')}"
        for m in to_summarise
    )

    system_prompt = (
        "You are a memory compression engine. "
        "Distill the conversation transcript below into a concise summary "
        "that captures all facts, decisions, and actionable items. "
        "Omit pleasantries. Use bullet points. Max 200 words."
    )

    try:
        response = call_with_rotation(
            task="compress context",
            task_type="logic",
            messages=[{"role": "user", "content": transcript}],
            system=system_prompt,
            max_tokens=min(500, MAX_TOKENS // 4),
        )
        summary = ""
        if hasattr(response, "content"):
            summary = response.content[0].text.strip()
        else:
            summary = str(response).strip()
    except Exception as exc:
        _log.error("Context compression failed: %s", exc, exc_info=True)
        summary = f"[Compression failed: {exc}]\n{transcript[:500]}"

    compressed = [
        {
            "role": "system",
            "content": f"[SESSION MEMORY — compressed from {len(to_summarise)} turns]\n{summary}",
        },
        *verbatim,
    ]
    _log.info(
        "Compressed %d → %d messages (%d words preserved)",
        len(messages),
        len(compressed),
        sum(len(m.get("content", "").split()) for m in verbatim),
    )
    return compressed


__all__ = ["should_compress", "compress"]
