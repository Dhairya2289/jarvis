"""Tests for ObsidianBrain."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from jarvis_v3.obsidian_brain import ObsidianBrain


@pytest.fixture
def brain(tmp_path: Path) -> ObsidianBrain:
    return ObsidianBrain(vault_path=tmp_path)


# -------------------------------------------------------------------------- #
# create_note
# -------------------------------------------------------------------------- #

def test_create_note_writes_frontmatter_and_content(brain: ObsidianBrain) -> None:
    """Created note has YAML frontmatter followed by body."""
    path = brain.create_note(
        "Hello",
        "This is the body.",
        folder="general",
        tags=["greeting", "test"],
        metadata={"author": "jarvis"},
    )
    assert path.exists()
    text = path.read_text()
    assert text.startswith("---\n")
    assert "created:" in text
    assert "modified:" in text
    assert "tags:" in text
    assert "- greeting" in text
    assert "This is the body." in text


def test_create_note_raises_if_exists(brain: ObsidianBrain) -> None:
    """Creating the same note twice raises FileExistsError."""
    brain.create_note("Dup", "content")
    with pytest.raises(FileExistsError):
        brain.create_note("Dup", "other content")


# -------------------------------------------------------------------------- #
# read_note
# -------------------------------------------------------------------------- #

def test_read_note_parses_frontmatter(brain: ObsidianBrain) -> None:
    """read_note returns parsed YAML in the frontmatter key."""
    brain.create_note(
        "ReadMe",
        "Hello world.",
        folder="docs",
        tags=["doc", "read"],
        metadata={"priority": "high"},
    )
    result = brain.read_note("ReadMe", folder="docs")
    assert result["frontmatter"]["tags"] == ["doc", "read"]
    assert result["frontmatter"]["priority"] == "high"
    assert result["content"] == "Hello world."
    assert isinstance(result["path"], Path)


def test_read_note_raises_if_missing(brain: ObsidianBrain) -> None:
    """Reading a non-existent note raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        brain.read_note("DoesNotExist")


# -------------------------------------------------------------------------- #
# update_note
# -------------------------------------------------------------------------- #

def test_update_note_modifies_content_and_timestamp(brain: ObsidianBrain) -> None:
    """update_note replaces body and advances modified timestamp."""
    p = brain.create_note("Updatable", "original content", tags=["old"])

    result1 = brain.read_note("Updatable")
    time.sleep(0.01)  # ensure mtime differs
    brain.update_note("Updatable", content="updated content", tags=["new"])

    result2 = brain.read_note("Updatable")
    assert result2["content"] == "updated content"
    assert result2["frontmatter"]["tags"] == ["new"]
    assert result2["frontmatter"]["modified"] != result1["frontmatter"]["created"]


def test_update_note_only_metadata(brain: ObsidianBrain) -> None:
    """update_note with no content arg only touches frontmatter."""
    brain.create_note("MetaOnly", "keep this", tags=["v1"])
    brain.update_note("MetaOnly", tags=["v2"])

    result = brain.read_note("MetaOnly")
    assert result["content"] == "keep this"
    assert result["frontmatter"]["tags"] == ["v2"]


def test_update_note_raises_if_missing(brain: ObsidianBrain) -> None:
    """Updating a non-existent note raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        brain.update_note("Ghost", content="nope")


# -------------------------------------------------------------------------- #
# list_notes
# -------------------------------------------------------------------------- #

def test_list_notes_returns_correct_count(brain: ObsidianBrain) -> None:
    """list_notes counts all notes across folders."""
    brain.create_note("A", "a content", folder="alpha")
    brain.create_note("B", "b content", folder="beta")
    brain.create_note("C", "c content", folder="alpha")

    all_notes = brain.list_notes()
    assert len(all_notes) == 3

    alpha_notes = brain.list_notes(folder="alpha")
    assert len(alpha_notes) == 2


def test_list_notes_includes_frontmatter_and_excerpt(brain: ObsidianBrain) -> None:
    """list_notes result has frontmatter and excerpt keys."""
    brain.create_note("Excerpt", "first line second line", folder="general", tags=["t1"])
    results = brain.list_notes(folder="general")
    assert len(results) == 1
    assert results[0]["frontmatter"]["tags"] == ["t1"]
    assert "first line" in results[0]["excerpt"]


# -------------------------------------------------------------------------- #
# search
# -------------------------------------------------------------------------- #

def test_search_finds_by_content(brain: ObsidianBrain) -> None:
    """search matches substring in body."""
    brain.create_note("Target", "needle in a haystack", folder="general")
    results = brain.search("needle")
    assert len(results) == 1
    assert results[0]["name"] == "Target"


def test_search_finds_by_tag(brain: ObsidianBrain) -> None:
    """search matches substring in frontmatter tags."""
    brain.create_note("T1", "content A", folder="general", tags=["alpha", "beta"])
    brain.create_note("T2", "content B", folder="general", tags=["beta", "gamma"])
    results = brain.search("alpha")
    assert len(results) == 1
    assert results[0]["name"] == "T1"


def test_search_finds_by_name(brain: ObsidianBrain) -> None:
    """search matches note name."""
    brain.create_note("UniquelyNamed", "some content", folder="general")
    results = brain.search("Uniquely")
    assert len(results) == 1


def test_search_respects_folder(brain: ObsidianBrain) -> None:
    """search with folder= restricts to that folder."""
    brain.create_note("SearchableInAlpha", "word", folder="alpha")
    brain.create_note("SearchableInBeta", "word", folder="beta")
    results = brain.search("word", folder="alpha")
    assert len(results) == 1
    assert results[0]["folder"] == "alpha"


# -------------------------------------------------------------------------- #
# link
# -------------------------------------------------------------------------- #

def test_link_adds_backlink_syntax(brain: ObsidianBrain) -> None:
    """link appends [[to_note]] to from_note body."""
    brain.create_note("Source", "already has some content", folder="general")
    brain.link("Source", "Target", from_folder="general")
    result = brain.read_note("Source")
    assert "[[Target]]" in result["content"]


def test_link_creates_target_if_missing(brain: ObsidianBrain) -> None:
    """link creates the target note if it doesn't exist."""
    brain.link("From", "AutoCreated", from_folder="general")
    result = brain.read_note("AutoCreated", folder="general")
    assert result["path"].exists()


# -------------------------------------------------------------------------- #
# get_daily_note
# -------------------------------------------------------------------------- #

def test_get_daily_note_creates_daily_folder_and_note(brain: ObsidianBrain) -> None:
    """get_daily_note creates daily/ and the YYYY-MM-DD.md file."""
    path = brain.get_daily_note()
    assert path.exists()
    assert path.parent.name == "daily"
    assert path.suffix == ".md"
    text = path.read_text()
    assert "type: daily" in text
    assert "tags:" in text


def test_get_daily_note_idempotent(brain: ObsidianBrain) -> None:
    """Calling get_daily_note twice returns the same path without error."""
    p1 = brain.get_daily_note()
    p2 = brain.get_daily_note()
    assert p1 == p2


# -------------------------------------------------------------------------- #
# append_daily
# -------------------------------------------------------------------------- #

def test_append_daily_appends_text(brain: ObsidianBrain) -> None:
    """append_daily adds a timestamped bullet to today's daily note."""
    path = brain.get_daily_note()
    initial = path.read_text()

    brain.append_daily("finished the task")
    after = path.read_text()
    assert after.startswith(initial)
    assert "- [" in after
    assert "finished the task" in after


def test_append_daily_returns_path(brain: ObsidianBrain) -> None:
    """append_daily returns the daily note path."""
    path = brain.append_daily("test entry")
    assert path.name.startswith("20")  # YYYY-MM-DD
    assert path.parent.name == "daily"