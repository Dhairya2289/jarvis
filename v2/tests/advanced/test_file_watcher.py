"""Tests for file_watcher.py."""
from pathlib import Path
from file_watcher import _ingest


def test_ingest_skips_unsupported(tmp_path):
    bad = tmp_path / "data.bin"
    bad.write_text("hello")
    _ingest(bad)
    # No crash is the contract here
