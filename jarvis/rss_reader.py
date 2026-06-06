"""RSS Feed Reader — poll feeds, store entries, write to Obsidian daily notes."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import feedparser

__all__ = ["FeedEntry", "RSSReader"]

log = logging.getLogger(__name__)


# -------------------------------------------------------------------------- #
# Data
# -------------------------------------------------------------------------- #

@dataclass
class FeedEntry:
    """A single entry from an RSS feed."""

    title: str
    link: str
    summary: str
    published: datetime
    feed_name: str

    def to_markdown(self) -> str:
        """Return a markdown-formatted list item for this entry."""
        date_str = self.published.strftime("%Y-%m-%d %H:%M")
        return (
            f"- [{self.title}]({self.link}) "
            f"\\[{self.feed_name} · {date_str}\\]\n"
            f"  {self.summary[:200]}"
        )


# -------------------------------------------------------------------------- #
# RSSReader
# -------------------------------------------------------------------------- #

class RSSReader:
    """
    Poll RSS feeds, store entries in SQLite, write new entries to Obsidian.

    Deduplication is by (link, title). Only entries not already in the DB
    are returned by ``fetch_all`` and written to Obsidian.
    """

    def __init__(self, db_path: Path = None, feeds: list[str] = None) -> None:
        from jarvis.config import BASE_DIR
        self.db_path = Path(db_path) if db_path else BASE_DIR / "rss.db"
        self.feeds = feeds if feeds is not None else ["https://hnrss.org/frontpage"]
        self._init_db()

    # ------------------------------------------------------------------ #
    # DB helpers
    # ------------------------------------------------------------------ #

    def _init_db(self) -> None:
        """Create the entries table if it does not exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS feed_entries (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    title       TEXT NOT NULL,
                    link        TEXT NOT NULL,
                    summary     TEXT NOT NULL,
                    published   TEXT NOT NULL,
                    feed_name   TEXT NOT NULL,
                    UNIQUE(link, title)
                )
                """
            )
            conn.commit()
        log.debug("RSS DB initialised at %s", self.db_path)

    def _insert_entries(self, entries: list[FeedEntry]) -> None:
        """Insert entries, ignoring duplicates."""
        with sqlite3.connect(self.db_path) as conn:
            for e in entries:
                try:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO feed_entries
                            (title, link, summary, published, feed_name)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (e.title, e.link, e.summary, e.published.isoformat(), e.feed_name),
                    )
                except Exception as exc:
                    log.warning("Failed to insert entry '%s': %s", e.title, exc)
            conn.commit()

    def _seen_entries(self) -> set[tuple[str, str]]:
        """Return all (link, title) pairs currently in the DB."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT link, title FROM feed_entries"
            ).fetchall()
        return {(link, title) for link, title in rows}

    # ------------------------------------------------------------------ #
    # fetch_all
    # ------------------------------------------------------------------ #

    def fetch_all(self) -> list[FeedEntry]:
        """
        Fetch all feeds, return only *new* entries not yet in the DB.

        Uses ``feedparser.parse`` internally so it can be mocked in tests.
        """
        seen = self._seen_entries()
        new_entries: list[FeedEntry] = []

        for feed_url in self.feeds:
            log.debug("Fetching feed: %s", feed_url)
            try:
                parsed = feedparser.parse(feed_url)
            except Exception as exc:
                log.warning("Failed to parse feed %s: %s", feed_url, exc)
                continue

            feed_title = _get_feed_title(parsed)
            entries = _parse_entries(parsed, feed_title)

            for entry in entries:
                key = (entry.link, entry.title)
                if key not in seen:
                    new_entries.append(entry)
                    seen.add(key)  # prevent duplicates within the same run

        self._insert_entries(new_entries)
        log.info(
            "fetch_all: %d new entries from %d feeds",
            len(new_entries),
            len(self.feeds),
        )
        return new_entries

    # ------------------------------------------------------------------ #
    # write_to_obsidian
    # ------------------------------------------------------------------ #

    def write_to_obsidian(self, entries: list[FeedEntry], daily_note: Path) -> None:
        """
        Append ``entries`` to ``daily_note`` (an Obsidian daily note path).

        Creates the file (with a minimal frontmatter) if it does not exist.
        Appends each entry as a markdown bullet with link, feed name, and
        summary excerpt.
        """
        daily_note = Path(daily_note)
        daily_note.parent.mkdir(parents=True, exist_ok=True)

        if not daily_note.exists():
            date_str = daily_note.stem  # YYYY-MM-DD
            frontmatter = (
                f"---\n"
                f"created: {datetime.now(timezone.utc).isoformat()}\n"
                f"modified: {datetime.now(timezone.utc).isoformat()}\n"
                f"tags: [rss, daily]\n"
                f"type: daily\n"
                f"---\n"
                f"# {date_str}\n\n"
                f"## RSS Entries\n\n"
            )
            daily_note.write_text(frontmatter, encoding="utf-8")

        existing = daily_note.read_text(encoding="utf-8") if daily_note.exists() else ""

        unique_entries = [e for e in entries if e.link not in existing]
        if not unique_entries:
            log.debug("All %d entries already in %s, skipping", len(entries), daily_note)
            return

        lines = [e.to_markdown() for e in unique_entries]
        section = "\n".join(lines) + "\n"
        daily_note.write_text(existing + section, encoding="utf-8")
        log.info("Wrote %d entries to %s", len(unique_entries), daily_note)

    # ------------------------------------------------------------------ #
    # get_digest
    # ------------------------------------------------------------------ #

    def get_digest(self, since: datetime) -> str:
        """
        Return a markdown-formatted digest of all entries published after ``since``.
        """
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT title, link, summary, published, feed_name
                  FROM feed_entries
                 WHERE published >= ?
                 ORDER BY published DESC
                """,
                (since.isoformat(),),
            ).fetchall()

        if not rows:
            return "No new feed entries."

        parts = [f"## Feed Digest ({since.strftime('%Y-%m-%d %H:%M')} onward)\n"]
        for title, link, summary, published, feed_name in rows:
            pub_dt = _parse_dt(published)
            parts.append(f"- [{title}]({link}) \\[{feed_name} · {pub_dt.strftime('%Y-%m-%d %H:%M')}\\]")
            if summary:
                parts.append(f"  {summary[:200]}")
            parts.append("")

        return "\n".join(parts).rstrip()


# -------------------------------------------------------------------------- #
# Internal parsing helpers
# -------------------------------------------------------------------------- #

def _get_feed_title(parsed: Any) -> str:
    """Extract feed title from a feedparser result."""
    return (
        getattr(parsed.feed, "title", None) or
        getattr(parsed.feed, "link", None) or
        "Unknown Feed"
    )


def _parse_dt(value: Any) -> datetime:
    """Parse an RSS date string into a UTC datetime."""
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(value)
    except Exception:
        pass
    # fallback
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def _parse_entries(parsed: Any, feed_name: str) -> list[FeedEntry]:
    """Convert feedparser entries to FeedEntry objects."""
    entries: list[FeedEntry] = []
    for entry in parsed.entries:
        title = getattr(entry, "title", "No title") or "No title"
        link = getattr(entry, "link", "") or ""
        summary_raw = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
        # Strip HTML tags from summary
        import re
        summary = re.sub(r"<[^>]+>", "", summary_raw).strip()

        published_raw = getattr(entry, "published", None) or getattr(entry, "updated", None)
        published = _parse_dt(published_raw) if published_raw else datetime.now(timezone.utc)

        entries.append(
            FeedEntry(
                title=title,
                link=link,
                summary=summary,
                published=published,
                feed_name=feed_name,
            )
        )
    return entries

def get_unread_items(limit: int = 20) -> list[dict]:
    """Fetch recent RSS entries and return them as plain dicts."""
    reader = RSSReader()
    entries = reader.fetch_all()
    return [
        {
            "title": e.title,
            "link": e.link,
            "summary": e.summary,
            "published": e.published.isoformat(),
            "feed_name": e.feed_name,
        }
        for e in entries[:limit]
    ]
