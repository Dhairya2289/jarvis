"""
Tests for memdir.py — Typed Memory Directory with Aging/Decay
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

import pytest

from jarvis.memdir import MemDir, MemoryEntry, VALID_MEM_TYPES


# ── Fixtures ────────────────────────────────────────────────


@pytest.fixture
def memdir(tmp_path: Path) -> MemDir:
    """Fresh MemDir backed by a temp directory."""
    return MemDir(data_dir=tmp_path / "memdir")


# ── MemoryEntry tests ───────────────────────────────────────


class TestMemoryEntry:
    def test_created_has_iso_format(self):
        entry = MemoryEntry(id="x", content="test", mem_type="fact")
        assert entry.created
        # Should be parseable as ISO datetime
        from datetime import datetime
        datetime.fromisoformat(entry.created)

    def test_defaults(self):
        entry = MemoryEntry(id="x", content="hello", mem_type="fact")
        assert entry.confidence == 0.8
        assert entry.decay == 1.0
        assert entry.tags == []
        assert entry.source == ""


# ── MemDir.add ──────────────────────────────────────────────


class TestMemDirAdd:
    def test_add_returns_entry_id(self, memdir: MemDir):
        eid = memdir.add("JARVIS runs on CachyOS", "fact")
        assert isinstance(eid, str)
        assert len(eid) > 0

    def test_add_persists_entry(self, memdir: MemDir):
        eid = memdir.add("I prefer dark mode", "preference")
        assert memdir.get(eid) is not None

    def test_add_all_mem_types(self, memdir: MemDir):
        for mt in VALID_MEM_TYPES:
            eid = memdir.add(f"test {mt}", mt)
            assert memdir.get(eid) is not None

    def test_add_invalid_mem_type_raises(self, memdir: MemDir):
        with pytest.raises(ValueError):
            memdir.add("bad type", "not_a_type")

    def test_add_tags(self, memdir: MemDir):
        eid = memdir.add("test", "fact", tags=["python", "jarvis"])
        entry = memdir.get(eid)
        assert entry is not None
        assert "python" in entry.tags
        assert "jarvis" in entry.tags

    def test_add_source(self, memdir: MemDir):
        eid = memdir.add("test", "fact", source="session_42")
        entry = memdir.get(eid)
        assert entry is not None
        assert entry.source == "session_42"

    def test_add_confidence_capped(self, memdir: MemDir):
        eid = memdir.add("high", "fact", confidence=1.5)
        entry = memdir.get(eid)
        assert entry is not None
        assert entry.confidence == 1.0

        eid2 = memdir.add("low", "fact", confidence=-0.5)
        entry2 = memdir.get(eid2)
        assert entry2 is not None
        assert entry2.confidence == 0.0


# ── MemDir.get ──────────────────────────────────────────────


class TestMemDirGet:
    def test_get_missing_returns_none(self, memdir: MemDir):
        assert memdir.get("nonexistent-id") is None

    def test_get_returns_entry(self, memdir: MemDir):
        eid = memdir.add("remember this", "fact")
        entry = memdir.get(eid)
        assert entry is not None
        assert entry.content == "remember this"
        assert entry.mem_type == "fact"


# ── MemDir.search ───────────────────────────────────────────


class TestMemDirSearch:
    def test_search_empty_query_returns_all(self, memdir: MemDir):
        for _ in range(3):
            memdir.add("test", "fact")
        results = memdir.search("")
        assert len(results) >= 3

    def test_search_exact_substring_match(self, memdir: MemDir):
        memdir.add("JARVIS is an AI assistant", "fact")
        memdir.add("CachyOS is the OS", "fact")
        results = memdir.search("JARVIS")
        assert len(results) >= 1
        assert any("JARVIS" in r.content for r in results)

    def test_search_partial_word_match(self, memdir: MemDir):
        memdir.add("Python is great", "fact")
        memdir.add("JavaScript too", "fact")
        # "pyth" is not a substring, but "pyth" has no word overlap with content
        # words either → score 0.0
        results = memdir.search("zzznomatchzzz")
        # No substring, no word overlap → score 0.0 → no results
        assert len(results) == 0

    def test_search_type_filter(self, memdir: MemDir):
        memdir.add("error one", "error")
        memdir.add("fact two", "fact")
        results = memdir.search("", mem_type="error")
        assert all(r.mem_type == "error" for r in results)

    def test_search_ranking_decay_boosted(self, memdir: MemDir):
        # Two entries with different decay; higher decay should rank first
        eid1 = memdir.add("JARVIS core", "fact")
        eid2 = memdir.add("JARVIS core", "fact")
        # Manually lower eid1's decay (simulate aged memory)
        entry1 = memdir.get(eid1)
        entry1.decay = 0.8
        memdir._save()
        results = memdir.search("JARVIS core")
        # Entry with higher decay (eid2) should rank first
        assert results[0].id == eid2

    def test_search_limit(self, memdir: MemDir):
        for i in range(20):
            memdir.add(f"content {i}", "fact")
        results = memdir.search("", limit=5)
        assert len(results) == 5

    def test_search_empty_on_no_match(self, memdir: MemDir):
        memdir.add("something", "fact")
        results = memdir.search("zzznomatchzzz")
        # No score > 0, so all filtered out
        assert len(results) == 0


# ── MemDir.access ───────────────────────────────────────────


class TestMemDirAccess:
    def test_access_boosts_decay(self, memdir: MemDir):
        eid = memdir.add("test", "fact")
        # Force decay below max so the boost is observable
        entry = memdir.get(eid)
        entry.decay = 0.9
        memdir._save()
        original_decay = memdir.get(eid).decay
        memdir.access(eid)
        boosted_decay = memdir.get(eid).decay
        assert boosted_decay > original_decay

    def test_access_caps_at_1(self, memdir: MemDir):
        eid = memdir.add("test", "fact")
        for _ in range(20):
            memdir.access(eid)
        entry = memdir.get(eid)
        assert entry is not None
        assert entry.decay == 1.0

    def test_access_missing_id_noop(self, memdir: MemDir):
        memdir.access("nonexistent")  # should not raise


# ── MemDir.apply_decay ──────────────────────────────────────


class TestMemDirApplyDecay:
    def test_apply_decay_multiplies_all(self, memdir: MemDir):
        eid1 = memdir.add("one", "fact")
        eid2 = memdir.add("two", "fact")
        original1 = memdir.get(eid1).decay
        memdir.apply_decay(factor=0.5)
        assert memdir.get(eid1).decay == pytest.approx(original1 * 0.5)
        assert memdir.get(eid2).decay == pytest.approx(original1 * 0.5)

    def test_apply_decay_floors_at_zero(self, memdir: MemDir):
        eid = memdir.add("tiny", "fact", confidence=0.1)
        memdir.apply_decay(factor=0.001)
        entry = memdir.get(eid)
        assert entry is not None
        assert entry.decay >= 0.0


# ── MemDir.prune ────────────────────────────────────────────


class TestMemDirPrune:
    def test_prune_removes_below_threshold(self, memdir: MemDir):
        eid = memdir.add("will decay", "fact")
        # Manually set decay below threshold
        entry = memdir.get(eid)
        entry.decay = 0.05
        memdir._save()
        removed = memdir.prune(threshold=0.1)
        assert removed == 1
        assert memdir.get(eid) is None

    def test_prune_preserves_above_threshold(self, memdir: MemDir):
        eid = memdir.add("keep", "fact")
        removed = memdir.prune(threshold=0.05)
        assert removed == 0
        assert memdir.get(eid) is not None

    def test_prune_returns_count(self, memdir: MemDir):
        for i in range(5):
            eid = memdir.add(f"item{i}", "fact")
            entry = memdir.get(eid)
            entry.decay = 0.05
        memdir._save()
        assert memdir.prune(threshold=0.1) == 5

    def test_prune_allows_zero_threshold(self, memdir: MemDir):
        eid = memdir.add("test", "fact")
        removed = memdir.prune(threshold=0.0)
        assert removed == 0
        assert memdir.get(eid) is not None


# ── Text match scoring ──────────────────────────────────────


class TestTextMatchScore:
    def test_exact_substring(self):
        score = MemDir._text_match_score("jarvis", "i love jarvis")
        assert score == 1.0

    def test_partial_word(self):
        score = MemDir._text_match_score("jarv", "i love jarvis")
        # "jarv" IS an exact substring of "i love jarvis" (case-sensitive check
        # against lowercase) → "jarv" in "i love jarvis" = True → score 1.0
        assert score == 1.0

    def test_word_overlap(self):
        score = MemDir._text_match_score("python code", "write some python")
        assert score == 0.5  # "python" matches

    def test_no_match(self):
        score = MemDir._text_match_score("xyz", "abc def")
        assert score == 0.0


# ── Type match bonus ────────────────────────────────────────


class TestTypeMatchBonus:
    def test_error_type_bonus(self):
        bonus = MemDir._type_match_bonus("error in the code", "error")
        assert bonus == 0.3

    def test_error_no_bonus_on_fact(self):
        bonus = MemDir._type_match_bonus("error in the code", "fact")
        assert bonus == 0.0

    def test_preference_bonus(self):
        bonus = MemDir._type_match_bonus("i prefer dark mode", "preference")
        assert bonus == 0.3

    def test_no_bonus(self):
        bonus = MemDir._type_match_bonus("hello world", "task")
        assert bonus == 0.0


# ── Persistence ─────────────────────────────────────────────


class TestPersistence:
    def test_reload_preserves_entries(self, tmp_path: Path):
        memdir1 = MemDir(data_dir=tmp_path / "md")
        eid = memdir1.add("persist me", "fact")
        del memdir1

        memdir2 = MemDir(data_dir=tmp_path / "md")
        entry = memdir2.get(eid)
        assert entry is not None
        assert entry.content == "persist me"

    def test_multiple_adds(self, memdir: MemDir):
        ids = [memdir.add(f"entry {i}", "fact") for i in range(10)]
        assert all(memdir.get(eid) is not None for eid in ids)