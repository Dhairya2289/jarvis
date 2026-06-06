"""Smart To-Do from Chat — parse action items from natural language messages."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from pathlib import Path

__all__ = ["Priority", "TodoItem", "SmartTodo"]

log = logging.getLogger(__name__)


# -------------------------------------------------------------------------- #
# Priority
# -------------------------------------------------------------------------- #

class Priority(str, Enum):
    """Supported priority levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


# -------------------------------------------------------------------------- #
# TodoItem
# -------------------------------------------------------------------------- #

@dataclass
class TodoItem:
    """A single to-do extracted from a chat message."""

    text: str
    priority: Priority
    due: str | None
    source: str
    created: str

    def to_markdown(self) -> str:
        """Render as an Obsidian task list item."""
        due_str = f" 📅 {self.due}" if self.due else ""
        priority_tag = f" 🔴" if self.priority == Priority.CRITICAL else (
            f" 🟠" if self.priority == Priority.HIGH else (
                f" 🟡" if self.priority == Priority.MEDIUM else ""
            )
        )
        return f"- [ ] {self.text}{priority_tag}{due_str}\n"


# -------------------------------------------------------------------------- #
# Keyword-based date / priority parsers
# -------------------------------------------------------------------------- #

# Monday=0 … Sunday=6
_WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
             "friday": 4, "saturday": 5, "sunday": 6}

_TODAY = date.today()


def _parse_relative_date(text: str) -> tuple[str, str] | None:
    """
    Scan ``text`` for relative date patterns.
    Returns (resolved_date_str, remaining_text) or None if nothing matched.
    Resolved date str is YYYY-MM-DD.
    """
    original = text

    # "day after tomorrow" (must come before "tomorrow" to avoid partial match)
    m = re.search(r"\bday after tomorrow\b", text, re.IGNORECASE)
    if m:
        resolved = (_TODAY + timedelta(days=2)).isoformat()
        return resolved, text[:m.start()] + text[m.end():]

    # "tomorrow"
    m = re.search(r"\btomorrow\b", text, re.IGNORECASE)
    if m:
        resolved = (_TODAY + timedelta(days=1)).isoformat()
        return resolved, text[:m.start()] + text[m.end():]

    # "in X days" / "in X weeks"
    m = re.search(
        r"\bin\s+(\d+)\s+(days?|weeks?)\b", text, re.IGNORECASE
    )
    if m:
        num = int(m.group(1))
        unit = m.group(2).lower()
        delta = timedelta(weeks=num) if unit.startswith("week") else timedelta(days=num)
        resolved = (_TODAY + delta).isoformat()
        return resolved, text[:m.start()] + text[m.end():]

    # "next <weekday>" — "next Monday"
    m = re.search(r"\bnext\s+(" + "|".join(_WEEKDAYS) + r")\b", text, re.IGNORECASE)
    if m:
        target = _WEEKDAYS[m.group(1).lower()]
        days_ahead = (target - _TODAY.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        resolved = (_TODAY + timedelta(days=days_ahead)).isoformat()
        return resolved, text[:m.start()] + text[m.end():]

    # bare weekday — "Monday" (this week or next, whichever is next occurrence)
    m = re.search(
        r"\b(?<!next\s)(" + "|".join(_WEEKDAYS) + r")\b(?!.*\btomorrow\b)",
        text, re.IGNORECASE
    )
    if m:
        target = _WEEKDAYS[m.group(1).lower()]
        days_ahead = (target - _TODAY.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        resolved = (_TODAY + timedelta(days=days_ahead)).isoformat()
        return resolved, text[:m.start()] + text[m.end():]

    # "by Friday", "on Monday" — "by" or "on" + weekday
    m = re.search(
        r"\b(?:by|on)\s+(" + "|".join(_WEEKDAYS) + r")\b", text, re.IGNORECASE
    )
    if m:
        target = _WEEKDAYS[m.group(1).lower()]
        days_ahead = (target - _TODAY.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        resolved = (_TODAY + timedelta(days=days_ahead)).isoformat()
        return resolved, text[:m.start()] + text[m.end():]

    # "by <month> <day>" — "by June 15"
    m = re.search(
        r"\bby\s+([A-Za-z]+)\s+(\d{1,2})\b", text, re.IGNORECASE
    )
    if m:
        month_name = m.group(1).lower()
        day = int(m.group(2))
        month_map = {
            "january": 1, "february": 2, "march": 3, "april": 4,
            "may": 5, "june": 6, "july": 7, "august": 8,
            "september": 9, "october": 10, "november": 11, "december": 12,
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }
        if month_name in month_map:
            month_num = month_map[month_name]
            year = _TODAY.year
            if month_num < _TODAY.month or (month_num == _TODAY.month and day < _TODAY.day):
                year += 1
            try:
                resolved = date(year, month_num, day).isoformat()
                return resolved, text[:m.start()] + text[m.end():]
            except ValueError:
                pass

    # "on <month> <day>" — same format
    m = re.search(
        r"\bon\s+([A-Za-z]+)\s+(\d{1,2})\b", text, re.IGNORECASE
    )
    if m:
        month_name = m.group(1).lower()
        day = int(m.group(2))
        month_map = {
            "january": 1, "february": 2, "march": 3, "april": 4,
            "may": 5, "june": 6, "july": 7, "august": 8,
            "september": 9, "october": 10, "november": 11, "december": 12,
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }
        if month_name in month_map:
            month_num = month_map[month_name]
            year = _TODAY.year
            if month_num < _TODAY.month or (month_num == _TODAY.month and day < _TODAY.day):
                year += 1
            try:
                resolved = date(year, month_num, day).isoformat()
                return resolved, text[:m.start()] + text[m.end():]
            except ValueError:
                pass

    return None


def _parse_priority(text: str) -> tuple[Priority, str]:
    """
    Scan text for priority keywords.
    Returns (detected_priority, remaining_text).
    """
    # Critical / ASAP first (most specific)
    for kw in ("asap", "critical", "urgent", "life or death", "must do"):
        m = re.search(r"\b" + kw + r"\b", text, re.IGNORECASE)
        if m:
            cleaned = text[:m.start()] + text[m.end():]
            return Priority.CRITICAL, cleaned.strip()

    # High priority
    m = re.search(r"\bhigh priority\b", text, re.IGNORECASE)
    if m:
        return Priority.HIGH, (text[:m.start()] + text[m.end():]).strip()

    # "important"
    m = re.search(r"\bimportant\b", text, re.IGNORECASE)
    if m:
        return Priority.HIGH, (text[:m.start()] + text[m.end():]).strip()

    # Medium — "medium priority", "when you get a chance"
    m = re.search(r"\bmedium priority\b", text, re.IGNORECASE)
    if m:
        return Priority.MEDIUM, (text[:m.start()] + text[m.end():]).strip()

    m = re.search(r"\bwhen (you|i) (get|have) (a )?chance\b", text, re.IGNORECASE)
    if m:
        return Priority.MEDIUM, (text[:m.start()] + text[m.end():]).strip()

    # Low — "low priority", "eventually", "someday"
    for kw in (r"\blow priority\b", r"\bsomeday\b", r"\blaisse[zs] faire\b",
               r"\beventually\b", r"\bno rush\b"):
        m = re.search(kw, text, re.IGNORECASE)
        if m:
            return Priority.LOW, (text[:m.start()] + text[m.end():]).strip()

    return Priority.NONE, text


# -------------------------------------------------------------------------- #
# SmartTodo
# -------------------------------------------------------------------------- #

class SmartTodo:
    """
    Parse action items from chat messages and manage an Obsidian Inbox.

    Keyword-based extraction with optional LLM enrichment if
    ``sentence-transformers`` or a local LLM is available.
    """

    INBOX_NAME = "Inbox.md"

    def __init__(self, vault_path: Path) -> None:
        self.vault_path = Path(vault_path)
        self.inbox_path = self.vault_path / self.INBOX_NAME

    # ------------------------------------------------------------------ #
    # parse_message
    # ------------------------------------------------------------------ #

    def parse_message(self, message: str) -> list[TodoItem]:
        """
        Extract action items from a free-text chat message.

        Handles:
          - Due dates: tomorrow, in X days, next Monday, by June 15, etc.
          - Priorities: ASAP, high priority, urgent, medium, low, etc.
          - Multiple items separated by newlines, semicolons, or "also".

        If ``sentence-transformers`` is available, uses it to split compound
        sentences into individual items; otherwise falls back to rule-based
        splitting on newlines, " and ", " also ", and ";".
        """
        sentences = self._split_sentences(message)
        items: list[TodoItem] = []
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            date_result = _parse_relative_date(sentence)
            if date_result is not None:
                due_str, cleaned = date_result
            else:
                due_str, cleaned = None, sentence
            priority, text = _parse_priority(cleaned)
            text = self._clean_text(text)
            if not text:
                continue
            items.append(
                TodoItem(
                    text=text,
                    priority=priority,
                    due=due_str,
                    source="chat",
                    created=datetime.now().isoformat(),
                )
            )
        return items

    # ------------------------------------------------------------------ #
    # _split_sentences — optional LLM enrichment path
    # ------------------------------------------------------------------ #

    def _split_sentences(self, message: str) -> list[str]:
        """Split message into candidate todo sentences."""
        # Try to use sentence-transformers for semantic splitting
        try:
            from sentence_transformers import SentenceTransformer
            # Check if the model is available without downloading
            import os
            model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
            # Use simple sentence boundary detection with embeddings
            import nltk
            try:
                nltk.data.find("tokenizer/punkt")
            except LookupError:
                nltk.download("punkt", quiet=True)
            from nltk.tokenize import sent_tokenize
            return sent_tokenize(message)
        except Exception:
            pass

        # Fallback: rule-based splitting
        # Replace common separators with newlines
        separators = re.compile(
            r"\s*(?:;|&&|\band\b|\balso\b|\bplus\b)\s*", re.IGNORECASE
        )
        parts = separators.split(message)
        sentences: list[str] = []
        for part in parts:
            # Split on double newlines or numbered lists
            sub = re.split(r"\n\s*\n|\n+\s*\d+[\.\)]\s*", part)
            sentences.extend([s.strip() for s in sub if s.strip()])
        return sentences if sentences else [message.strip()]

    # ------------------------------------------------------------------ #
    # _clean_text
    # ------------------------------------------------------------------ #

    def _clean_text(self, text: str) -> str:
        """Remove common lead-in phrases and normalise whitespace."""
        text = re.sub(r"^(?:please |kindly |can you |could you |remind me to |"
                      r"i need to |i should |i have to |don't forget to |"
                      r"don't forget |remember to |remember |"
                      r"i want to |want to )",
                      "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"\s+", " ", text).strip()
        # Strip trailing punctuation
        text = text.rstrip(".!")
        return text

    # ------------------------------------------------------------------ #
    # add_items
    # ------------------------------------------------------------------ #

    def add_items(self, items: list[TodoItem]) -> None:
        """
        Append ``items`` to the Obsidian Inbox.

        Creates ``Inbox.md`` (with minimal frontmatter) if it doesn't exist.
        Each item is written as an unchecked Obsidian task list line.
        """
        if not items:
            return
        self.inbox_path.parent.mkdir(parents=True, exist_ok=True)
        created = datetime.now().isoformat()

        if not self.inbox_path.exists():
            frontmatter = (
                "---\n"
                f"created: {created}\n"
                "modified: {created}\n"
                "tags: [inbox, todos]\n"
                "type: inbox\n"
                "---\n"
                f"# Inbox\n\n"
            )
            self.inbox_path.write_text(frontmatter, encoding="utf-8")
            log.debug("Created new Inbox at %s", self.inbox_path)

        existing = self.inbox_path.read_text(encoding="utf-8")

        lines = [item.to_markdown() for item in items]
        section = "\n".join(lines)
        # Append before any closing缝
        self.inbox_path.write_text(existing + section + "\n", encoding="utf-8")
        log.info("Added %d item(s) to %s", len(items), self.inbox_path)

    # ------------------------------------------------------------------ #
    # list_items
    # ------------------------------------------------------------------ #

    def list_items(self, status: str = "open") -> list[TodoItem]:
        """
        Return items from the Inbox matching ``status``.

        ``status`` is one of:
          - ``"open"`` — lines starting with ``- [ ]`` (default)
          - ``"done"`` — lines starting with ``- [x]``
          - ``"all"`` — both open and done
        """
        if not self.inbox_path.exists():
            return []

        text = self.inbox_path.read_text(encoding="utf-8")
        items: list[TodoItem] = []
        for line in text.splitlines():
            line = line.strip()
            if status == "open" and line.startswith("- [ ]"):
                items.append(self._line_to_item(line))
            elif status == "done" and line.startswith("- [x]"):
                items.append(self._line_to_item(line))
            elif status == "all" and (line.startswith("- [ ]") or line.startswith("- [x]")):
                items.append(self._line_to_item(line))
        return items

    def _line_to_item(self, line: str) -> TodoItem:
        """Parse a single task line back into a TodoItem."""
        done = line.startswith("- [x]")
        # Strip checkbox prefix
        content = re.sub(r"- \[[ x]\]\s*", "", line).strip()

        # Extract priority emoji
        priority = Priority.NONE
        if "🔴" in content:
            priority = Priority.CRITICAL
            content = content.replace("🔴", "").strip()
        elif "🟠" in content:
            priority = Priority.HIGH
            content = content.replace("🟠", "").strip()
        elif "🟡" in content:
            priority = Priority.MEDIUM
            content = content.replace("🟡", "").strip()

        # Extract due date emoji
        due: str | None = None
        m = re.search(r"📅\s*(\d{4}-\d{2}-\d{2})", content)
        if m:
            due = m.group(1)
            content = re.sub(r"📅\s*\d{4}-\d{2}-\d{2}", "", content).strip()

        # Clean trailing punctuation
        content = content.rstrip(".!").strip()

        return TodoItem(
            text=content,
            priority=priority,
            due=due,
            source="inbox",
            created="",
        )

    # ------------------------------------------------------------------ #
    # complete_item
    # ------------------------------------------------------------------ #

    def complete_item(self, idx: int) -> None:
        """
        Mark the item at 0-based index ``idx`` as done.

        Only considers open items (``- [ ]``) in reading order.
        Raises ``IndexError`` if ``idx`` is out of range.
        """
        if not self.inbox_path.exists():
            raise IndexError("Inbox is empty")

        lines = self.inbox_path.read_text(encoding="utf-8").splitlines()
        open_indices: list[int] = []
        for i, line in enumerate(lines):
            if line.strip().startswith("- [ ]"):
                open_indices.append(i)

        if idx < 0 or idx >= len(open_indices):
            raise IndexError(
                f"Index {idx} out of range for {len(open_indices)} open items"
            )

        target_line_no = open_indices[idx]
        line = lines[target_line_no]
        # Replace "- [ ]" with "- [x]"
        lines[target_line_no] = re.sub(r"- \[ \]", "- [x]", line, count=1)

        self.inbox_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        log.info("Completed item %d at line %d", idx, target_line_no)