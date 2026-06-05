"""JARVIS Training Data Collector

Ingests Obsidian session notes into instruction/response pairs
for supervised fine-tuning.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from jarvis.config import BASE_DIR

_log = logging.getLogger(__name__)
SESSIONS_DIR = BASE_DIR / "obsidian" / "sessions"


def _extract_pairs(note_text: str) -> list[dict[str, str]]:
    """Extract user/assistant turns from a session markdown note."""
    pairs: list[dict[str, str]] = []
    # Match "## User" or "[USER]" blocks
    user_blocks = re.split(r"(?=##\s*User|<user>|\[USER\])", note_text, flags=re.IGNORECASE)
    for block in user_blocks:
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        if len(lines) < 2:
            continue
        # Find the first line that looks like a user query
        if any(h in lines[0].lower() for h in ["user", "human"]):
            instruction = "\n".join(lines[1:]).strip()
        else:
            instruction = block
        # Look for assistant response after this block (simplistic)
        assistant = ""
        pairs.append({"instruction": instruction, "response": assistant})
    return pairs


def _load_session_notes() -> list[Path]:
    if not SESSIONS_DIR.exists():
        return []
    return sorted(SESSIONS_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime)


def collect_dataset(*, min_chars: int = 50) -> list[dict[str, str]]:
    """Collect instruction-response pairs from Obsidian session notes.

    Returns a list of dicts with keys 'instruction', 'response'.
    """
    notes = _load_session_notes()
    _log.info("Found %d session notes in %s", len(notes), SESSIONS_DIR)
    pairs: list[dict[str, str]] = []
    for note in notes:
        try:
            text = note.read_text(encoding="utf-8", errors="replace")
            # Naive extraction: paragraphs longer than min_chars become instructions
            # Actual responses are harder to reconstruct without structured format
            # We use a simple heuristic: split by double newlines, odd=instruction, even=response
            blocks = [b.strip() for b in text.split("\n\n") if len(b.strip()) >= min_chars]
            for i in range(0, len(blocks) - 1, 2):
                pairs.append({
                    "instruction": blocks[i][:512],
                    "response": blocks[i + 1][:512],
                })
        except Exception as exc:
            _log.warning("Failed to read %s: %s", note, exc)

    _log.info("Collected %d instruction/response pairs", len(pairs))
    return pairs


def save_dataset(pairs: list[dict[str, Any]], path: Path | None = None) -> Path:
    if path is None:
        path = BASE_DIR / "training" / "dataset.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for p in pairs:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    _log.info("Dataset saved: %s (%d rows)", path, len(pairs))
    return path


def load_dataset(path: Path | None = None) -> list[dict[str, Any]]:
    if path is None:
        path = BASE_DIR / "training" / "dataset.jsonl"
    if not path.exists():
        return []
    pairs = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            pairs.append(json.loads(line))
    return pairs
