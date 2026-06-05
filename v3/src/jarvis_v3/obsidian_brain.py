"""Obsidian Brain — JARVIS's canonical memory layer stored as structured markdown."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

__all__ = ["ObsidianBrain"]

log = logging.getLogger(__name__)

# -------------------------------------------------------------------------- #
# Frontmatter helpers
# -------------------------------------------------------------------------- #

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def _parse_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    """Return (frontmatter_dict, body_content) from a markdown string."""
    m = FRONTMATTER_RE.match(raw)
    if m:
        fm = yaml.safe_load(m.group(1)) or {}
        body = raw[m.end() :]
    else:
        fm = {}
        body = raw
    return fm, body


def _build_frontmatter(fm: dict[str, Any]) -> str:
    """Return the --- fences + YAML block for a frontmatter dict."""
    return "---\n" + yaml.safe_dump(fm, sort_keys=False).rstrip() + "\n---\n"


def _note_path(vault: Path, name: str, folder: str) -> Path:
    sanitized = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "_", name)
    return vault / folder / f"{sanitized}.md"


# -------------------------------------------------------------------------- #
# Note result dataclass (returned by read_note / search)
# -------------------------------------------------------------------------- #

NOTE_RE = re.compile(r"^(.*?)\.md$", re.DOTALL)


# -------------------------------------------------------------------------- #
# ObsidianBrain
# -------------------------------------------------------------------------- #


class ObsidianBrain:
    """
    A local-first note-taking brain backed by an Obsidian-compatible vault.

    Every note is a ``.md`` file with YAML frontmatter::

        ---
        created: 2026-01-01T00:00:00Z
        modified: 2026-01-01T00:00:00Z
        tags: [general, idea]
        type: note
        ---

        Note body goes here.
    """

    def __init__(self, vault_path: Path | None = None) -> None:
        self.vault: Path = vault_path or (Path.home() / ".jarvis" / "obsidian")
        self.vault.mkdir(parents=True, exist_ok=True)
        log.info("ObsidianBrain initialised at %s", self.vault)

    # ------------------------------------------------------------------ #
    # create_note
    # ------------------------------------------------------------------ #

    def create_note(
        self,
        name: str,
        content: str,
        *,
        folder: str = "general",
        tags: list[str] | None = None,
        metadata: dict | None = None,
    ) -> Path:
        """
        Create a new note ``name`` in ``folder`` with ``content``.

        Returns the absolute path of the created file.
        Raises ``FileExistsError`` if the note already exists.
        """
        path = _note_path(self.vault, name, folder)
        if path.exists():
            raise FileExistsError(f"Note already exists: {path}")

        folder_path = self.vault / folder
        folder_path.mkdir(parents=True, exist_ok=True)

        now = datetime.now(timezone.utc).isoformat()
        frontmatter: dict[str, Any] = {
            "created": now,
            "modified": now,
            "tags": tags or [],
            "type": "note",
        }
        if metadata:
            frontmatter.update(metadata)

        fm_block = _build_frontmatter(frontmatter)
        text = fm_block + content + "\n"

        path.write_text(text, encoding="utf-8")
        log.info("Created note %s", path)
        return path

    # ------------------------------------------------------------------ #
    # read_note
    # ------------------------------------------------------------------ #

    def read_note(self, name: str, folder: str = "general") -> dict[str, Any]:
        """
        Read note ``name`` from ``folder`` and return a result dict::

            {
                "frontmatter": { ... },   # parsed YAML, never None
                "content": "...",
                "path": Path("..."),
            }

        Raises ``FileNotFoundError`` if the note does not exist.
        """
        path = _note_path(self.vault, name, folder)
        if not path.exists():
            raise FileNotFoundError(f"Note not found: {path}")

        raw = path.read_text(encoding="utf-8")
        frontmatter, content = _parse_frontmatter(raw)
        log.debug("Read note %s", path)
        return {
            "frontmatter": frontmatter,
            "content": content.rstrip("\n"),
            "path": path,
        }

    # ------------------------------------------------------------------ #
    # update_note
    # ------------------------------------------------------------------ #

    def update_note(
        self,
        name: str,
        content: str | None = None,
        *,
        folder: str = "general",
        tags: list[str] | None = None,
        metadata: dict | None = None,
    ) -> Path:
        """
        Update an existing note's body and/or frontmatter fields.

        At least one of ``content`` or ``tags`` or ``metadata`` must be given.
        Always updates the ``modified`` timestamp in frontmatter.

        Returns the note path.
        Raises ``FileNotFoundError`` if the note does not exist.
        """
        path = _note_path(self.vault, name, folder)
        if not path.exists():
            raise FileNotFoundError(f"Note not found: {path}")

        raw = path.read_text(encoding="utf-8")
        frontmatter, body = _parse_frontmatter(raw)

        if content is not None:
            body = content

        now = datetime.now(timezone.utc).isoformat()
        frontmatter["modified"] = now

        if tags is not None:
            frontmatter["tags"] = tags

        if metadata:
            frontmatter.update(metadata)

        fm_block = _build_frontmatter(frontmatter)
        path.write_text(fm_block + body + "\n", encoding="utf-8")
        log.info("Updated note %s", path)
        return path

    # ------------------------------------------------------------------ #
    # list_notes
    # ------------------------------------------------------------------ #

    def list_notes(self, folder: str | None = None) -> list[dict[str, Any]]:
        """
        List every note under ``folder`` (or the whole vault if ``folder`` is None).

        Each dict in the returned list has ``name``, ``folder``, ``path``,
        ``frontmatter``, and ``excerpt`` (first 120 chars of body).
        """
        root: Path
        if folder is not None:
            root = self.vault / folder
        else:
            root = self.vault

        results: list[dict[str, Any]] = []

        for md_file in sorted(root.rglob("*.md")):
            try:
                raw = md_file.read_text(encoding="utf-8")
            except Exception as exc:
                log.warning("Could not read %s: %s", md_file, exc)
                continue

            frontmatter, body = _parse_frontmatter(raw)
            rel = md_file.relative_to(self.vault)
            parts = rel.parts
            note_folder = str(Path(*parts[:-1])) if len(parts) > 1 else "."
            results.append(
                {
                    "name": md_file.stem,
                    "folder": note_folder,
                    "path": md_file,
                    "frontmatter": frontmatter,
                    "excerpt": body[:120].replace("\n", " ").strip(),
                    "content": body,
                }
            )

        log.debug("Listed %d notes from %s", len(results), root)
        return results

    # ------------------------------------------------------------------ #
    # search
    # ------------------------------------------------------------------ #

    def search(
        self, query: str, *, folder: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Substring-search ``query`` across note content and frontmatter tags.

        Matching is case-insensitive. Returns the same dict shape as
        ``list_notes`` for each match.
        """
        q = query.lower()
        results: list[dict[str, Any]] = []

        for note in self.list_notes(folder=folder):
            body = note["content"][:500].lower()  # index only start of body for perf
            tags: list[str] = note["frontmatter"].get("tags") or []
            tag_text = " ".join(tags).lower()

            if q in body or q in tag_text or q in note["name"].lower():
                results.append(note)

        log.debug("Search '%s' in folder=%s returned %d results", query, folder, len(results))
        return results

    # ------------------------------------------------------------------ #
    # link
    # ------------------------------------------------------------------ #

    def link(
        self,
        from_note: str,
        to_note: str,
        *,
        from_folder: str = "general",
        to_folder: str = "general",
    ) -> None:
        """
        Add a wikilink ``[[to_note]]`` to the end of ``from_note``.

        Creates ``to_note`` as an empty note if it does not yet exist.
        """
        # ensure target exists
        try:
            self.read_note(to_note, folder=to_folder)
        except FileNotFoundError:
            self.create_note(to_note, "", folder=to_folder)

        path = _note_path(self.vault, from_note, from_folder)
        if path.exists():
            raw = path.read_text(encoding="utf-8")
            _, body = _parse_frontmatter(raw)
        else:
            now = datetime.now(timezone.utc).isoformat()
            fm: dict[str, Any] = {
                "created": now,
                "modified": now,
                "tags": [],
                "type": "note",
            }
            body = ""
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = _build_frontmatter(fm)

        backlink = f"[[{to_note}]]\n"
        path.write_text(raw + body.rstrip("\n") + "\n" + backlink, encoding="utf-8")
        log.info("Linked %s -> [[%s]]", path.name, to_note)

    # ------------------------------------------------------------------ #
    # get_daily_note
    # ------------------------------------------------------------------ #

    def get_daily_note(self) -> Path:
        """
        Create (if missing) and return the path of today's daily note.

        Daily notes live in the ``daily/`` folder and are named ``YYYY-MM-DD.md``.
        Frontmatter always includes ``type: daily``.
        """
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        folder = "daily"
        path = self.vault / folder / f"{today}.md"

        if path.exists():
            log.debug("Daily note already exists: %s", path)
            return path

        folder_path = self.vault / folder
        folder_path.mkdir(parents=True, exist_ok=True)

        now = datetime.now(timezone.utc).isoformat()
        frontmatter: dict[str, Any] = {
            "created": now,
            "modified": now,
            "tags": ["daily"],
            "type": "daily",
            "date": today,
        }

        fm_block = _build_frontmatter(frontmatter)
        path.write_text(fm_block + f"# {today}\n", encoding="utf-8")
        log.info("Created daily note %s", path)
        return path

    # ------------------------------------------------------------------ #
    # append_daily
    # ------------------------------------------------------------------ #

    def append_daily(self, text: str) -> Path:
        """
        Append ``text`` (one line per entry, timestamped) to today's daily note.

        Returns the daily note path.
        """
        path = self.get_daily_note()
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        entry = f"- [{timestamp}] {text}\n"

        raw = path.read_text(encoding="utf-8")
        path.write_text(raw + entry, encoding="utf-8")
        log.info("Appended to daily note %s", path)
        return path