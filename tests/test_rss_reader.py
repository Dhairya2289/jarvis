"""Tests for RSS reader — feedparser is mocked so no network calls are made."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from jarvis.rss_reader import FeedEntry, RSSReader


# -------------------------------------------------------------------------- #
# Fake parsed feed objects (mirroring feedparser structure)
# -------------------------------------------------------------------------- #

def _make_feed(title: str, link: str) -> SimpleNamespace:
    return SimpleNamespace(title=title, link=link)


def _make_entry(
    title: str,
    link: str,
    summary: str,
    published: str,
) -> SimpleNamespace:
    return SimpleNamespace(
        title=title,
        link=link,
        summary=summary,
        published=published,
        updated=None,
    )


FAKE_FEED_XML = """
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <link>https://example.com/feed</link>
    <item>
      <title>Article One</title>
      <link>https://example.com/article-1</link>
      <summary>Summary of article one.</summary>
      <published>Thu, 01 Jun 2026 10:00:00 +0000</published>
    </item>
    <item>
      <title>Article Two</title>
      <link>https://example.com/article-2</link>
      <summary>Summary of <b>article two</b> with HTML.</summary>
      <published>Thu, 01 Jun 2026 11:00:00 +0000</published>
    </item>
  </channel>
</rss>
"""


def _make_parsed_result(
    feed_title: str,
    feed_link: str,
    entries: list[SimpleNamespace],
) -> SimpleNamespace:
    """Return a fake feedparser.parse() result."""
    return SimpleNamespace(
        feed=_make_feed(feed_title, feed_link),
        entries=entries,
    )


# -------------------------------------------------------------------------- #
# Fixture
# -------------------------------------------------------------------------- #

@pytest.fixture
def rss(tmp_path: Path) -> RSSReader:
    db = tmp_path / "feeds.db"
    return RSSReader(db_path=db, feeds=["https://example.com/feed"])


# -------------------------------------------------------------------------- #
# FeedEntry dataclass
# -------------------------------------------------------------------------- #

def test_feed_entry_to_markdown() -> None:
    """FeedEntry.to_markdown() produces a correctly formatted bullet."""
    entry = FeedEntry(
        title="Hello World",
        link="https://example.com/hello",
        summary="A short summary.",
        published=datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc),
        feed_name="Test Feed",
    )
    md = entry.to_markdown()
    assert "[Hello World](https://example.com/hello)" in md
    assert "Test Feed" in md
    assert "A short summary." in md


# -------------------------------------------------------------------------- #
# RSSReader.init_db
# -------------------------------------------------------------------------- #

def test_init_db_creates_table(rss: RSSReader, tmp_path: Path) -> None:
    """DB is created and has the entries table."""
    import sqlite3
    with sqlite3.connect(rss.db_path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='feed_entries'"
        ).fetchall()
    assert len(rows) == 1


# -------------------------------------------------------------------------- #
# RSSReader.fetch_all (mocked)
# -------------------------------------------------------------------------- #

def test_fetch_all_returns_new_entries(rss: RSSReader) -> None:
    """fetch_all returns FeedEntry objects parsed from the mocked feed."""
    entry1 = _make_entry(
        "Article One",
        "https://example.com/article-1",
        "Summary of article one.",
        "Thu, 01 Jun 2026 10:00:00 +0000",
    )
    entry2 = _make_entry(
        "Article Two",
        "https://example.com/article-2",
        "Summary of article two.",
        "Thu, 01 Jun 2026 11:00:00 +0000",
    )
    fake_result = _make_parsed_result("Test Feed", "https://example.com/feed", [entry1, entry2])

    with patch("jarvis.rss_reader.feedparser.parse", return_value=fake_result):
        entries = rss.fetch_all()

    assert len(entries) == 2
    titles = {e.title for e in entries}
    assert titles == {"Article One", "Article Two"}
    links = {e.link for e in entries}
    assert links == {"https://example.com/article-1", "https://example.com/article-2"}
    assert all(e.feed_name == "Test Feed" for e in entries)
    assert all(e.summary for e in entries)


def test_fetch_all_deduplicates_by_link_and_title(rss: RSSReader) -> None:
    """Same (link, title) pair is not returned twice across two fetch_all calls."""
    entry = _make_entry(
        "Dup Article",
        "https://example.com/dup",
        "Summary.",
        "Thu, 01 Jun 2026 12:00:00 +0000",
    )
    fake_result = _make_parsed_result("Test Feed", "https://example.com/feed", [entry])

    with patch("jarvis.rss_reader.feedparser.parse", return_value=fake_result):
        first = rss.fetch_all()
        second = rss.fetch_all()

    assert len(first) == 1
    assert len(second) == 0  # deduplicated


def test_fetch_all_deduplicates_within_same_call(rss: RSSReader) -> None:
    """If the same entry appears twice in a single feed, it is returned once."""
    entry = _make_entry(
        "Only Once",
        "https://example.com/only-once",
        "Summary.",
        "Thu, 01 Jun 2026 12:00:00 +0000",
    )
    # Same entry twice
    fake_result = _make_parsed_result("Test Feed", "https://example.com/feed", [entry, entry])

    with patch("jarvis.rss_reader.feedparser.parse", return_value=fake_result):
        entries = rss.fetch_all()

    # Should appear only once (deduped within the run)
    assert len(entries) == 1
    assert entries[0].title == "Only Once"


def test_fetch_all_strips_html_from_summary(rss: RSSReader) -> None:
    """HTML tags in summary are stripped."""
    entry = _make_entry(
        "HTML Article",
        "https://example.com/html",
        "Summary with <b>bold</b> and <i>italic</i> text.",
        "Thu, 01 Jun 2026 13:00:00 +0000",
    )
    fake_result = _make_parsed_result("Test Feed", "https://example.com/feed", [entry])

    with patch("jarvis.rss_reader.feedparser.parse", return_value=fake_result):
        entries = rss.fetch_all()

    assert "<b>" not in entries[0].summary
    assert "<i>" not in entries[0].summary
    assert "bold" in entries[0].summary


def test_fetch_all_empty_feed(rss: RSSReader) -> None:
    """A feed with no entries returns an empty list."""
    fake_result = _make_parsed_result("Empty Feed", "https://empty.example.com", [])
    with patch("jarvis.rss_reader.feedparser.parse", return_value=fake_result):
        entries = rss.fetch_all()
    assert entries == []


# -------------------------------------------------------------------------- #
# RSSReader.write_to_obsidian
# -------------------------------------------------------------------------- #

def test_write_to_obsidian_creates_file(rss: RSSReader, tmp_path: Path) -> None:
    """write_to_obsidian creates the daily note if it does not exist."""
    daily = tmp_path / "2026-06-01.md"
    entry = FeedEntry(
        title="Obsidian Test",
        link="https://example.com/obs",
        summary="Summary for obsidian.",
        published=datetime(2026, 6, 1, 9, 0, 0, tzinfo=timezone.utc),
        feed_name="Test Feed",
    )
    rss.write_to_obsidian([entry], daily)

    assert daily.exists()
    text = daily.read_text()
    assert "2026-06-01" in text
    assert "Obsidian Test" in text
    assert "https://example.com/obs" in text


def test_write_to_obsidian_appends_without_duplicates(rss: RSSReader, tmp_path: Path) -> None:
    """Appending the same entries twice does not duplicate them in the file."""
    daily = tmp_path / "2026-06-02.md"
    entry = FeedEntry(
        title="Dup Test",
        link="https://example.com/dup",
        summary="Summary.",
        published=datetime(2026, 6, 2, 9, 0, 0, tzinfo=timezone.utc),
        feed_name="Test Feed",
    )
    rss.write_to_obsidian([entry], daily)
    rss.write_to_obsidian([entry], daily)

    text = daily.read_text()
    assert text.count("Dup Test") == 1


def test_write_to_obsidian_multiple_entries(rss: RSSReader, tmp_path: Path) -> None:
    """Multiple entries are all written to the daily note."""
    daily = tmp_path / "2026-06-03.md"
    entries = [
        FeedEntry(
            title=f"Entry {i}",
            link=f"https://example.com/entry-{i}",
            summary=f"Summary {i}.",
            published=datetime(2026, 6, 3, i, 0, 0, tzinfo=timezone.utc),
            feed_name="Test Feed",
        )
        for i in range(3)
    ]
    rss.write_to_obsidian(entries, daily)

    text = daily.read_text()
    for e in entries:
        assert e.title in text
        assert e.link in text


# -------------------------------------------------------------------------- #
# RSSReader.get_digest
# -------------------------------------------------------------------------- #

def test_get_digest_returns_entries_since(rss: RSSReader) -> None:
    """get_digest returns entries published after the given datetime."""
    # Pre-insert entries directly via the DB to avoid mocking fetch_all
    import sqlite3
    with sqlite3.connect(rss.db_path) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO feed_entries
                (title, link, summary, published, feed_name)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "Recent Article",
                "https://example.com/recent",
                "Recent summary.",
                datetime(2026, 6, 1, 14, 0, 0, tzinfo=timezone.utc).isoformat(),
                "Test Feed",
            ),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO feed_entries
                (title, link, summary, published, feed_name)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "Old Article",
                "https://example.com/old",
                "Old summary.",
                datetime(2026, 5, 30, 10, 0, 0, tzinfo=timezone.utc).isoformat(),
                "Test Feed",
            ),
        )
        conn.commit()

    since = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
    digest = rss.get_digest(since)

    assert "Recent Article" in digest
    assert "https://example.com/recent" in digest
    assert "Old Article" not in digest


def test_get_digest_empty_when_no_entries(rss: RSSReader) -> None:
    """get_digest returns a 'no entries' message when the DB is empty."""
    since = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
    digest = rss.get_digest(since)
    assert "No new feed entries" in digest


# -------------------------------------------------------------------------- #
# Dataclass field verification
# -------------------------------------------------------------------------- #

def test_feed_entry_has_all_required_fields() -> None:
    """FeedEntry dataclass has the five required fields."""
    entry = FeedEntry(
        title="T",
        link="L",
        summary="S",
        published=datetime.now(timezone.utc),
        feed_name="F",
    )
    assert entry.title == "T"
    assert entry.link == "L"
    assert entry.summary == "S"
    assert isinstance(entry.published, datetime)
    assert entry.feed_name == "F"