"""
memdir.py — Typed Memory Directory with Aging/Decay
─────────────────────────────────────────────────────
Inspired by Claude's memdir concept.

Each memory entry carries:
  • mem_type  — one of fact / preference / error / task / insight
  • confidence — 0.0–1.0, set at creation
  • decay      — 0.0–1.0, multiplied by 0.95 daily, boosted on access

Search ranks entries by:
  relevance_score = (text_match_score + type_match_bonus) * confidence * decay
"""

from __future__ import annotations

import json
import logging
import math
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_LOG = logging.getLogger(__name__)

DEFAULT_DATA_DIR = Path.home() / ".jarvis" / "memdir"

VALID_MEM_TYPES = frozenset({"fact", "preference", "error", "task", "insight"})


# ── Dataclasses ────────────────────────────────────────────


@dataclass
class MemoryEntry:
    """A single stored memory with typed metadata and decay tracking."""
    id: str
    content: str
    mem_type: str
    confidence: float = 0.8
    decay: float = 1.0
    created: str = ""
    last_accessed: str = ""
    tags: list[str] = field(default_factory=list)
    source: str = ""

    def __post_init__(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        if not self.created:
            self.created = now
        if not self.last_accessed:
            self.last_accessed = now


# ── MemDir ─────────────────────────────────────────────────


class MemDir:
    """
    Typed memory directory with JSON persistence and aging/decay.

    Parameters
    ----------
    data_dir : Path | None
        Directory for the memories.json store.
        Defaults to ``~/.jarvis/memdir/``.
    """

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = (data_dir or DEFAULT_DATA_DIR).expanduser()
        self._store_path = self._data_dir / "memories.json"
        self._entries: dict[str, MemoryEntry] = {}
        self._load()

    # ── Persistence ────────────────────────────────────────

    def _load(self) -> None:
        """Load entries from ``memories.json``."""
        if not self._store_path.exists():
            self._entries = {}
            return
        try:
            data = json.loads(self._store_path.read_text())
            self._entries = {
                k: MemoryEntry(**v) for k, v in data.items()
            }
        except Exception as exc:
            _LOG.warning("Failed to load memdir store: %s", exc)
            self._entries = {}

    def _save(self) -> None:
        """Persist entries to ``memories.json``."""
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            self._store_path.write_text(
                json.dumps({k: asdict(v) for k, v in self._entries.items()}, indent=2)
            )
        except Exception as exc:
            _LOG.warning("Failed to save memdir store: %s", exc)

    # ── CRUD ────────────────────────────────────────────────

    def add(
        self,
        content: str,
        mem_type: str,
        confidence: float = 0.8,
        tags: list[str] | None = None,
        source: str = "",
    ) -> str:
        """
        Store a new memory and return its entry ID.

        Also mirrors the entry to Obsidian Brain when available.
        """
        if mem_type not in VALID_MEM_TYPES:
            raise ValueError(f"Invalid mem_type {mem_type!r}; must be one of {VALID_MEM_TYPES}")
        confidence = float(max(0.0, min(1.0, confidence)))
        entry_id = str(uuid.uuid4())
        entry = MemoryEntry(
            id=entry_id,
            content=content,
            mem_type=mem_type,
            confidence=confidence,
            decay=1.0,
            created=datetime.now(timezone.utc).isoformat(),
            last_accessed=datetime.now(timezone.utc).isoformat(),
            tags=tags or [],
            source=source,
        )
        self._entries[entry_id] = entry
        self._save()
        self._write_to_obsidian(entry)
        return entry_id

    def get(self, entry_id: str) -> MemoryEntry | None:
        """Retrieve a single entry by ID, or None if not found."""
        return self._entries.get(entry_id)

    # ── Search ──────────────────────────────────────────────

    def search(
        self,
        query: str,
        *,
        mem_type: str | None = None,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        """
        Ranked search over all entries.

        Scoring
        -------
        text_match_score:
            exact substring match  → 1.0
            partial word match     → 0.5
            no match              → 0.0
        type_match_bonus:
            +0.3 if mem_type hint matches query intent heuristics
        Final score = (text_match_score + type_match_bonus) * confidence * decay
        """
        if not query and not mem_type:
            return list(self._entries.values())[:limit]

        scored: list[tuple[float, MemoryEntry]] = []
        query_lower = query.lower()

        for entry in self._entries.values():
            if mem_type and entry.mem_type != mem_type:
                continue

            # Text match
            text_score = self._text_match_score(query_lower, entry.content.lower())

            # Type bonus
            type_bonus = self._type_match_bonus(query_lower, entry.mem_type)

            raw_score = (text_score + type_bonus) * entry.confidence * entry.decay
            if raw_score > 0:
                scored.append((raw_score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:limit]]

    @staticmethod
    def _text_match_score(query: str, content: str) -> float:
        """Return 0.0 / 0.5 / 1.0 based on substring and word overlap."""
        if query in content:
            return 1.0
        query_words = set(query.split())
        content_words = set(content.split())
        if query_words & content_words:  # any word overlap
            return 0.5
        return 0.0

    @staticmethod
    def _type_match_bonus(query: str, mem_type: str) -> float:
        """+0.3 bonus when query contains type-associated keywords."""
        bonuses: dict[str, tuple[str, ...]] = {
            "fact":      ("fact", "know", "remember", "true", "info"),
            "preference": ("prefer", "like", "hate", "want", "settings"),
            "error":     ("error", "bug", "fail", "crash", "fix", "issue"),
            "task":      ("task", "todo", "do", "schedule", "remind"),
            "insight":   ("insight", "learned", "realised", "realized", "figured"),
        }
        keywords = bonuses.get(mem_type, ())
        if any(kw in query for kw in keywords):
            return 0.3
        return 0.0

    # ── Access tracking ─────────────────────────────────────

    def access(self, entry_id: str) -> None:
        """
        Update last_accessed timestamp and boost decay by +0.05 (max 1.0).
        """
        entry = self._entries.get(entry_id)
        if not entry:
            return
        entry.last_accessed = datetime.now(timezone.utc).isoformat()
        entry.decay = min(1.0, entry.decay + 0.05)
        self._save()

    # ── Decay & Prune ───────────────────────────────────────

    def apply_decay(self, factor: float = 0.95) -> None:
        """
        Multiply all decay scores by ``factor`` (intended for daily cron).

        Scores are floored at 0.0.
        """
        for entry in self._entries.values():
            entry.decay = max(0.0, entry.decay * factor)
        self._save()

    def prune(self, threshold: float = 0.1) -> int:
        """
        Remove entries whose decay < threshold.

        Returns the number of entries removed.
        """
        to_remove = [eid for eid, e in self._entries.items() if e.decay < threshold]
        for eid in to_remove:
            del self._entries[eid]
        if to_remove:
            self._save()
        return len(to_remove)

    # ── Obsidian mirror ─────────────────────────────────────

    def _write_to_obsidian(self, entry: MemoryEntry) -> None:
        """Write a memory entry to Obsidian Brain if available."""
        try:
            from jarvis_v3.obsidian_brain import ObsidianBrain
            brain = ObsidianBrain()
            brain.create_note(
                name=f"mem_{entry.id}",
                content=entry.content,
                folder="memory",
                tags=entry.tags or [],
                metadata={
                    "mem_type": entry.mem_type,
                    "confidence": entry.confidence,
                    "decay": entry.decay,
                    "source": entry.source,
                },
            )
        except Exception as exc:
            _LOG.debug("Obsidian mirror skipped (not available): %s", exc)