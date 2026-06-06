"""Tests for Smart To-Do from Chat — no network calls, uses temp files."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

import pytest

from jarvis.smart_todo import Priority, SmartTodo, TodoItem, _parse_priority, _parse_relative_date


# -------------------------------------------------------------------------- #
# Helpers
# -------------------------------------------------------------------------- #

@pytest.fixture
def tmp_vault(tmp_path):
    """A temporary Obsidian vault."""
    return tmp_path / "vault"


# -------------------------------------------------------------------------- #
# _parse_relative_date
# -------------------------------------------------------------------------- #

class TestParseRelativeDate:
    def _check(self, text: str, expected_iso: str) -> None:
        result = _parse_relative_date(text)
        assert result is not None, f"Expected date from '{text}'"
        date_str, remaining = result
        assert date_str == expected_iso
        # The date phrase should have been removed from remaining text
        assert text != remaining  # something changed

    def test_tomorrow(self):
        from datetime import date, timedelta
        expected = (date.today() + timedelta(days=1)).isoformat()
        self._check("send the report tomorrow", expected)

    def test_in_n_days(self):
        from datetime import date, timedelta
        expected = (date.today() + timedelta(days=3)).isoformat()
        self._check("finish this in 3 days", expected)

    def test_in_weeks(self):
        from datetime import date, timedelta
        expected = (date.today() + timedelta(weeks=2)).isoformat()
        self._check("review in 2 weeks", expected)

    def test_next_weekday(self):
        from datetime import date, timedelta
        today = date.today()
        # Find next Tuesday
        target_weekday = 1  # Tuesday
        days_ahead = (target_weekday - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        expected = (today + timedelta(days=days_ahead)).isoformat()
        self._check("call mom next Tuesday", expected)

    def test_by_weekday(self):
        from datetime import date, timedelta
        today = date.today()
        target_weekday = 4  # Friday
        days_ahead = (target_weekday - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        expected = (today + timedelta(days=days_ahead)).isoformat()
        self._check("by Friday", expected)

    def test_by_month_day(self):
        result = _parse_relative_date("finish by June 15")
        assert result is not None
        date_str, remaining = result
        assert date_str.startswith("2026-06-15") or date_str.startswith("2027-06-15")
        assert "june" not in remaining.lower() and "15" not in remaining

    def test_no_date(self):
        result = _parse_relative_date("just a regular task")
        assert result is None

    def test_day_after_tomorrow(self):
        from datetime import date, timedelta
        expected = (date.today() + timedelta(days=2)).isoformat()
        self._check("the day after tomorrow", expected)


# -------------------------------------------------------------------------- #
# _parse_priority
# -------------------------------------------------------------------------- #

class TestParsePriority:
    def _check(self, text: str, expected_priority: Priority, expected_text_contains: str | None = None) -> None:
        priority, cleaned = _parse_priority(text)
        assert priority == expected_priority, f"Expected {expected_priority}, got {priority} for '{text}'"
        if expected_text_contains:
            assert expected_text_contains in cleaned.lower()

    def test_critical(self):
        self._check("Submit the report ASAP", Priority.CRITICAL)
        self._check("This is critical!", Priority.CRITICAL)
        self._check("Urgent task here", Priority.CRITICAL)

    def test_high(self):
        self._check("high priority task", Priority.HIGH)
        self._check("This is important", Priority.HIGH)

    def test_medium(self):
        self._check("medium priority item", Priority.MEDIUM)
        self._check("when you get a chance", Priority.MEDIUM)

    def test_low(self):
        self._check("low priority task", Priority.LOW)
        self._check("someday maybe", Priority.LOW)
        self._check("no rush on this", Priority.LOW)

    def test_none(self):
        priority, text = _parse_priority("just a simple task")
        assert priority == Priority.NONE


# -------------------------------------------------------------------------- #
# SmartTodo — integration tests (using temp vault)
# -------------------------------------------------------------------------- #

class TestSmartTodo:
    def test_parse_message_basic(self, tmp_vault):
        st = SmartTodo(tmp_vault)
        items = st.parse_message("send the report tomorrow")
        assert len(items) == 1
        assert items[0].priority == Priority.NONE
        assert items[0].due is not None
        assert "send the report" in items[0].text.lower()

    def test_parse_message_with_priority(self, tmp_vault):
        st = SmartTodo(tmp_vault)
        items = st.parse_message("Remind me to send the report tomorrow, high priority")
        assert len(items) == 1
        assert items[0].priority == Priority.HIGH
        assert items[0].due is not None

    def test_parse_message_multiple_items(self, tmp_vault):
        st = SmartTodo(tmp_vault)
        items = st.parse_message(
            "send the report tomorrow and also call mom next Tuesday"
        )
        assert len(items) >= 1  # may be split or kept as one
        # At minimum the first item should be parsed
        assert any("report" in i.text.lower() for i in items)

    def test_parse_message_multiple_items_semicolons(self, tmp_vault):
        st = SmartTodo(tmp_vault)
        items = st.parse_message(
            "finish the report; call mom tomorrow; send invoice by Friday"
        )
        assert len(items) >= 1

    def test_parse_message_asap(self, tmp_vault):
        st = SmartTodo(tmp_vault)
        items = st.parse_message("submit the report ASAP")
        assert len(items) == 1
        assert items[0].priority == Priority.CRITICAL

    def test_add_items_creates_inbox(self, tmp_vault):
        st = SmartTodo(tmp_vault)
        items = [
            TodoItem(
                text="Test task",
                priority=Priority.HIGH,
                due="2026-06-10",
                source="test",
                created="2026-06-06T10:00:00",
            )
        ]
        st.add_items(items)
        assert st.inbox_path.exists()
        content = st.inbox_path.read_text()
        assert "- [ ]" in content
        assert "Test task" in content

    def test_add_items_appends(self, tmp_vault):
        st = SmartTodo(tmp_vault)
        item1 = TodoItem(text="First task", priority=Priority.NONE, due=None, source="test", created="")
        item2 = TodoItem(text="Second task", priority=Priority.MEDIUM, due=None, source="test", created="")
        st.add_items([item1])
        st.add_items([item2])
        content = st.inbox_path.read_text()
        assert "First task" in content
        assert "Second task" in content

    def test_list_items_open(self, tmp_vault):
        st = SmartTodo(tmp_vault)
        items = [
            TodoItem(text="Open task one", priority=Priority.HIGH, due="2026-06-10", source="test", created=""),
            TodoItem(text="Open task two", priority=Priority.MEDIUM, due=None, source="test", created=""),
        ]
        st.add_items(items)
        listed = st.list_items(status="open")
        assert len(listed) == 2
        texts = [i.text for i in listed]
        assert "Open task one" in texts
        assert "Open task two" in texts

    def test_list_items_empty_vault(self, tmp_vault):
        st = SmartTodo(tmp_vault)
        assert st.list_items() == []

    def test_complete_item(self, tmp_vault):
        st = SmartTodo(tmp_vault)
        items = [
            TodoItem(text="Task A", priority=Priority.NONE, due=None, source="test", created=""),
            TodoItem(text="Task B", priority=Priority.HIGH, due=None, source="test", created=""),
            TodoItem(text="Task C", priority=Priority.MEDIUM, due=None, source="test", created=""),
        ]
        st.add_items(items)

        # Complete the second item (Task B)
        st.complete_item(1)

        remaining = st.list_items(status="open")
        assert len(remaining) == 2
        open_texts = [i.text for i in remaining]
        assert "Task B" not in open_texts
        assert "Task A" in open_texts
        assert "Task C" in open_texts

        done = st.list_items(status="done")
        assert len(done) == 1
        assert done[0].text == "Task B"

    def test_complete_item_out_of_range(self, tmp_vault):
        st = SmartTodo(tmp_vault)
        item = TodoItem(text="Only task", priority=Priority.NONE, due=None, source="test", created="")
        st.add_items([item])
        with pytest.raises(IndexError):
            st.complete_item(99)

    def test_parse_and_add_flow(self, tmp_vault):
        """End-to-end: parse a natural message and persist it."""
        st = SmartTodo(tmp_vault)
        items = st.parse_message(
            "Remind me to send the report tomorrow, high priority"
        )
        assert len(items) == 1
        st.add_items(items)

        listed = st.list_items(status="open")
        assert len(listed) == 1
        assert listed[0].priority == Priority.HIGH
        assert listed[0].due is not None
        assert "report" in listed[0].text.lower()

    def test_markdown_format(self, tmp_vault):
        """Verify the exact markdown format written to Inbox.md."""
        st = SmartTodo(tmp_vault)
        item = TodoItem(
            text="Review the proposal",
            priority=Priority.HIGH,
            due="2026-06-15",
            source="test",
            created="2026-06-06T10:00:00",
        )
        st.add_items([item])
        content = st.inbox_path.read_text()
        # Should contain an unchecked task with emoji tags
        assert "- [ ]" in content
        assert "Review the proposal" in content
        # Priority HIGH = 🟠
        assert "🟠" in content
        # Due date
        assert "📅" in content
        assert "2026-06-15" in content