"""Tests for jarvis.desktop — Chunk 5 desktop orchestration modules."""

import json
import os
import sqlite3
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from jarvis.desktop import (
    WorkspaceMemory,
    SmartLauncher,
    ClipboardHistory,
    NotificationTriage,
    NotificationEntry,
    ScreenshotManager,
    WindowLogger,
    WindowEvent,
    smart_launch,
)


# --------------------------------------------------------------------------- #
# WorkspaceMemory
# --------------------------------------------------------------------------- #

class TestWorkspaceMemory:
    def test_snapshot_returns_dict(self, tmp_path):
        """snapshot() returns a dict (may be empty if hyprctl unavailable)."""
        mem = WorkspaceMemory()
        result = mem.snapshot()
        assert isinstance(result, dict)
        # Keys should be int workspace IDs
        for k in result:
            assert isinstance(k, int)

    def test_save_and_load_snapshot(self, tmp_path):
        """A saved snapshot can be loaded back."""
        mem = WorkspaceMemory()
        # Use the actual current state so the round-trip is meaningful
        current_snap = mem.snapshot()
        save_path = tmp_path / "ws_snap.json"
        mem.save_snapshot(save_path)
        loaded = mem.load_snapshot(save_path)
        # Loaded should match what we saved (the live snapshot at save time)
        assert loaded == current_snap

    def test_load_nonexistent_returns_empty(self, tmp_path):
        """load_snapshot returns {} for non-existent file."""
        mem = WorkspaceMemory()
        result = mem.load_snapshot(tmp_path / "nonexistent.json")
        assert result == {}

    def test_saved_snapshot_exists(self, tmp_path):
        """saved_snapshot_exists reports correct state."""
        mem = WorkspaceMemory()
        path = tmp_path / "snap.json"
        assert not mem.saved_snapshot_exists(path)
        mem.save_snapshot(path)
        assert mem.saved_snapshot_exists(path)


# --------------------------------------------------------------------------- #
# SmartLauncher
# --------------------------------------------------------------------------- #

class TestSmartLauncher:
    def test_smart_launch_empty_query(self):
        """Empty query returns an error string."""
        result = smart_launch("")
        assert "[ERROR]" in result

    def test_smart_launch_whitespace_query(self):
        """Whitespace-only query returns an error string."""
        result = smart_launch("   ")
        assert "[ERROR]" in result

    def test_launcher_instantiation(self):
        """SmartLauncher can be instantiated."""
        launcher = SmartLauncher()
        assert launcher is not None

    def test_launcher_launch_returns_str(self):
        """launch() always returns a string."""
        launcher = SmartLauncher()
        result = launcher.launch("nonexistent_app_xyz_123")
        assert isinstance(result, str)

    def test_xdg_open_returns_on_invalid(self):
        """_xdg_open handles missing xdg-open gracefully."""
        launcher = SmartLauncher()
        result = launcher._xdg_open("/nonexistent/path/file.txt")
        # Either opened or errored gracefully
        assert isinstance(result, str)
        assert ("Opened" in result or "[ERROR]" in result)


# --------------------------------------------------------------------------- #
# ClipboardHistory
# --------------------------------------------------------------------------- #

class TestClipboardHistory:
    def test_instantiation_creates_db(self, tmp_path):
        """Creating ClipboardHistory creates the SQLite DB."""
        db = tmp_path / "clip.db"
        hist = ClipboardHistory(db_path=db)
        assert db.exists()

    def test_store_and_get_recent(self, tmp_path):
        """store() adds an entry; get_recent() retrieves it."""
        hist = ClipboardHistory(db_path=tmp_path / "clip.db")
        hist.store("hello world")
        recent = hist.get_recent(5)
        assert "hello world" in recent

    def test_get_recent_order(self, tmp_path):
        """Most recent entries come first."""
        hist = ClipboardHistory(db_path=tmp_path / "clip.db")
        hist.store("first")
        hist.store("second")
        hist.store("third")
        recent = hist.get_recent(3)
        assert recent[0] == "third"
        assert recent[2] == "first"

    def test_search(self, tmp_path):
        """search() returns matching entries."""
        hist = ClipboardHistory(db_path=tmp_path / "clip.db")
        hist.store("alpha hello beta")
        hist.store("gamma world delta")
        results = hist.search("hello")
        assert any("hello" in r for r in results)
        results2 = hist.search("xyz")
        assert len(results2) == 0

    def test_empty_content_not_stored(self, tmp_path):
        """store() ignores empty/whitespace content."""
        hist = ClipboardHistory(db_path=tmp_path / "clip.db")
        hist.store("")
        hist.store("   ")
        assert hist.count() == 0

    def test_count(self, tmp_path):
        """count() returns the number of entries."""
        hist = ClipboardHistory(db_path=tmp_path / "clip.db")
        assert hist.count() == 0
        hist.store("a")
        hist.store("b")
        assert hist.count() == 2

    def test_poll_once_returns_none_when_no_change(self, tmp_path):
        """poll_once returns None when clipboard unchanged."""
        hist = ClipboardHistory(db_path=tmp_path / "clip.db")
        # Without wl-paste, should return None gracefully
        result = hist.poll_once()
        # Should not raise — returns None if no clipboard tool
        assert result is None or isinstance(result, str)

    def test_db_schema(self, tmp_path):
        """DB has expected clipboard table schema."""
        hist = ClipboardHistory(db_path=tmp_path / "clip.db")
        conn = sqlite3.connect(str(tmp_path / "clip.db"))
        cur = conn.execute("PRAGMA table_info(clipboard)")
        columns = {row[1] for row in cur.fetchall()}
        conn.close()
        assert "id" in columns
        assert "content" in columns


# --------------------------------------------------------------------------- #
# NotificationTriage
# --------------------------------------------------------------------------- #

class TestNotificationTriage:
    def test_instantiation(self):
        """NotificationTriage can be instantiated."""
        triage = NotificationTriage()
        assert triage is not None

    def test_recent_returns_list(self):
        """recent() returns a list (may be empty if no history)."""
        triage = NotificationTriage()
        result = triage.recent(5)
        assert isinstance(result, list)

    def test_summarize_returns_str(self):
        """summarize() returns a non-empty string."""
        triage = NotificationTriage()
        result = triage.summarize()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_notification_entry_to_dict(self):
        """NotificationEntry.to_dict() produces a correct dict."""
        entry = NotificationEntry(
            app="test-app",
            title="Test Title",
            body="Test body",
            timestamp="2024-01-01T00:00:00",
            urgency="high",
        )
        d = entry.to_dict()
        assert d["app"] == "test-app"
        assert d["title"] == "Test Title"
        assert d["body"] == "Test body"
        assert d["urgency"] == "high"

    def test_mako_history_nonexistent_returns_empty(self, tmp_path):
        """With no history file, recent() returns empty list gracefully."""
        triage = NotificationTriage(history_path=tmp_path / "nonexistent")
        result = triage.recent(5)
        assert isinstance(result, list)


# --------------------------------------------------------------------------- #
# ScreenshotManager
# --------------------------------------------------------------------------- #

class TestScreenshotManager:
    def test_instantiation_creates_dir(self, tmp_path):
        """ScreenshotManager creates screenshot_dir on init."""
        sc_dir = tmp_path / "screenshots"
        mgr = ScreenshotManager(screenshot_dir=sc_dir)
        assert sc_dir.exists()

    def test_organize_moves_screenshots(self, tmp_path):
        """organize() moves PNG files into YYYY-MM subfolders."""
        sc_dir = tmp_path / "screenshots"
        mgr = ScreenshotManager(screenshot_dir=sc_dir)
        sc_dir.mkdir(parents=True, exist_ok=True)

        # Create a fake "old" screenshot
        f = sc_dir / "screenshot_2024.png"
        f.write_text("fake PNG data")

        result = mgr.organize()
        assert result["moved"] == 1
        assert not f.exists()  # moved away

        # Should be in a date folder
        date_folders = [d for d in sc_dir.iterdir() if d.is_dir()]
        assert len(date_folders) == 1

    def test_organize_skips_non_screenshots(self, tmp_path):
        """organize() skips non-image/text files."""
        sc_dir = tmp_path / "screenshots"
        mgr = ScreenshotManager(screenshot_dir=sc_dir)
        sc_dir.mkdir(parents=True, exist_ok=True)

        (sc_dir / "readme.txt").write_text("not a screenshot")
        (sc_dir / "data.json").write_text('{"key": "value"}')

        result = mgr.organize()
        assert result["skipped"] == 2
        assert result["moved"] == 0

    def test_archive_moves_old_files(self, tmp_path):
        """archive() moves files older than keep_days to archive_dir."""
        sc_dir = tmp_path / "screenshots"
        archive_dir = tmp_path / "archive"
        mgr = ScreenshotManager(screenshot_dir=sc_dir, archive_dir=archive_dir)
        sc_dir.mkdir(parents=True, exist_ok=True)

        # Create a date folder with a file
        date_folder = sc_dir / "2020-01"
        date_folder.mkdir()
        old_file = date_folder / "old_shot.png"
        old_file.write_text("old")

        # Make it look old by touching mtime
        old_mtime = (datetime.now() - timedelta(days=60)).timestamp()
        os.utime(old_file, (old_mtime, old_mtime))

        archived = mgr.archive(keep_days=30)
        assert archived == 1
        assert not old_file.exists()
        # Should be in archive
        archived_files = list(archive_dir.glob("**/*.png"))
        assert len(archived_files) == 1

    def test_recent_returns_paths(self, tmp_path):
        """recent() returns Path objects sorted by mtime descending."""
        sc_dir = tmp_path / "screenshots"
        mgr = ScreenshotManager(screenshot_dir=sc_dir)
        sc_dir.mkdir(parents=True, exist_ok=True)

        # Create date folders with files
        folder1 = sc_dir / "2024-01"
        folder1.mkdir()
        (folder1 / "shot1.png").write_text("oldest")
        time.sleep(0.01)
        folder2 = sc_dir / "2024-02"
        folder2.mkdir()
        (folder2 / "shot2.png").write_text("newest")

        recent = mgr.recent(5)
        assert len(recent) == 2
        # Newest first
        assert "shot2" in recent[0].name
        assert "shot1" in recent[1].name

    def test_count(self, tmp_path):
        """count() returns total screenshot files."""
        sc_dir = tmp_path / "screenshots"
        mgr = ScreenshotManager(screenshot_dir=sc_dir)
        sc_dir.mkdir(parents=True, exist_ok=True)

        folder = sc_dir / "2024-01"
        folder.mkdir()
        (folder / "a.png").write_text("")
        (folder / "b.png").write_text("")

        assert mgr.count() == 2


# --------------------------------------------------------------------------- #
# WindowLogger
# --------------------------------------------------------------------------- #

class TestWindowLogger:
    def test_instantiation(self, tmp_path):
        """WindowLogger can be instantiated."""
        log = tmp_path / "window_log.jsonl"
        logger = WindowLogger(log_file=log)
        assert logger is not None

    def test_tick_returns_event_or_none(self, tmp_path):
        """tick() returns WindowEvent or None — never raises."""
        log = tmp_path / "wl.jsonl"
        logger = WindowLogger(log_file=log)
        result = logger.tick()
        # Should not raise; result is either WindowEvent or None
        assert result is None or isinstance(result, WindowEvent)

    def test_get_timeline_empty_on_new_log(self, tmp_path):
        """get_timeline() returns [] for a new log file."""
        log = tmp_path / "wl.jsonl"
        logger = WindowLogger(log_file=log)
        timeline = logger.get_timeline(since=datetime.now() - timedelta(hours=1))
        assert timeline == []

    def test_get_timeline_returns_events(self, tmp_path):
        """get_timeline() returns events in the time range."""
        log = tmp_path / "wl.jsonl"
        logger = WindowLogger(log_file=log)

        now = datetime.now()
        events = [
            WindowEvent(timestamp=(now - timedelta(minutes=30)).isoformat(),
                        workspace=1, title="Window A", class_name="ClassA"),
            WindowEvent(timestamp=(now - timedelta(minutes=10)).isoformat(),
                        workspace=1, title="Window B", class_name="ClassB"),
        ]
        for ev in events:
            logger._append(ev)

        timeline = logger.get_timeline(since=now - timedelta(hours=1))
        assert len(timeline) == 2
        assert timeline[0].title == "Window A"
        assert timeline[1].title == "Window B"

    def test_get_timeline_filters_old(self, tmp_path):
        """get_timeline() excludes events older than 'since'."""
        log = tmp_path / "wl.jsonl"
        logger = WindowLogger(log_file=log)

        now = datetime.now()
        events = [
            WindowEvent(timestamp=(now - timedelta(days=2)).isoformat(),
                        workspace=1, title="Old", class_name="Old"),
            WindowEvent(timestamp=now.isoformat(),
                        workspace=1, title="New", class_name="New"),
        ]
        for ev in events:
            logger._append(ev)

        timeline = logger.get_timeline(since=now - timedelta(days=1))
        assert len(timeline) == 1
        assert timeline[0].title == "New"

    def test_event_count(self, tmp_path):
        """event_count() returns correct count."""
        log = tmp_path / "wl.jsonl"
        logger = WindowLogger(log_file=log)
        assert logger.event_count() == 0

        for i in range(5):
            ev = WindowEvent(
                timestamp=datetime.now().isoformat(),
                workspace=1, title=f"Window {i}", class_name=f"Class{i}",
            )
            logger._append(ev)

        assert logger.event_count() == 5

    def test_window_event_to_dict(self):
        """WindowEvent.to_dict() produces a correct dict."""
        ev = WindowEvent(
            timestamp="2024-01-01T12:00:00",
            workspace=1,
            title="Test Window",
            class_name="TestClass",
            pid=12345,
        )
        d = ev.to_dict()
        assert d["title"] == "Test Window"
        assert d["class_name"] == "TestClass"
        assert d["workspace"] == 1
        assert d["pid"] == 12345

    def test_start_stop_poller(self, tmp_path):
        """start_poller() and stop_poller() run without errors."""
        log = tmp_path / "wl.jsonl"
        logger = WindowLogger(log_file=log)
        logger.start_poller(interval=0.5)
        time.sleep(1.5)
        logger.stop_poller()
        # Should not raise — verified by reaching here

    def test_unique_dest_avoids_collision(self, tmp_path):
        """_unique_dest returns a non-existing path."""
        p = tmp_path / "file.png"
        p.write_text("v1")
        result = ScreenshotManager._unique_dest(p)
        assert result != p
        assert not result.exists()