"""Tests for jarvis.file_search_index"""

import os
import sqlite3
import tempfile
import time
from pathlib import Path

import pytest

from jarvis.file_search_index import FileSearchIndex, SearchResult


class TestFileSearchIndexInit:
    def test_creates_db_file(self, tmp_path):
        db = tmp_path / "test.db"
        idx = FileSearchIndex(db)
        assert db.exists()

    def test_tables_exist(self, tmp_path):
        db = tmp_path / "test.db"
        idx = FileSearchIndex(db)
        conn = sqlite3.connect(str(db))
        cur = conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [r[0] for r in cur.fetchall()]
        conn.close()
        assert "files" in tables
        assert "fts_index" in tables


class TestScan:
    def test_scan_indexes_files(self, tmp_path):
        # Create a temp dir with known files
        root = tmp_path / "root"
        root.mkdir()
        (root / "alpha.txt").write_text("hello alpha")
        (root / "beta.py").write_text("print('beta')")
        sub = root / "subdir"
        sub.mkdir()
        (sub / "gamma.md").write_text("# gamma")

        db = tmp_path / "idx.db"
        idx = FileSearchIndex(db)
        count = idx.scan(root)

        assert count == 3
        results = idx.search("alpha")
        assert len(results) == 1
        assert "alpha.txt" in results[0].basename

    def test_scan_excludes_patterns(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        (root / "visible.txt").write_text("seen")
        git = root / ".git"
        git.mkdir()
        (git / "config").write_text("secret")

        db = tmp_path / "idx.db"
        idx = FileSearchIndex(db)
        count = idx.scan(root)

        # .git files should be excluded by default patterns
        assert count == 1
        paths = [r.path for r in idx.search("")]
        assert not any(".git" in p for p in paths)

    def test_scan_empty_dir(self, tmp_path):
        root = tmp_path / "empty"
        root.mkdir()
        db = tmp_path / "idx.db"
        idx = FileSearchIndex(db)
        count = idx.scan(root)
        assert count == 0

    def test_scan_returns_file_count(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        for i in range(20):
            (root / f"file_{i}.txt").write_text(f"content {i}")

        db = tmp_path / "idx.db"
        idx = FileSearchIndex(db)
        count = idx.scan(root)
        assert count == 20

    def test_scan_1000_files_performance(self, tmp_path):
        """Benchmark: 1000 files indexed in under 10 seconds."""
        root = tmp_path / "root"
        root.mkdir()
        for i in range(1000):
            sub = root / f"dir_{i % 10}"
            sub.mkdir(exist_ok=True)
            (sub / f"file_{i}.txt").write_text(f"content {i}")

        db = tmp_path / "idx.db"
        idx = FileSearchIndex(db)

        start = time.perf_counter()
        count = idx.scan(root)
        elapsed = time.perf_counter() - start

        assert count == 1000
        assert elapsed < 10.0, f"Scan took {elapsed:.1f}s, expected <10s"

    def test_scan_nested_files(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        (root / "a" / "b" / "c").mkdir(parents=True)
        (root / "a" / "b" / "c" / "deep.txt").write_text("deep")
        (root / "a" / "top.txt").write_text("top")

        db = tmp_path / "idx.db"
        idx = FileSearchIndex(db)
        count = idx.scan(root)
        assert count == 2


class TestSearch:
    def test_search_returns_results(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        (root / "hello_world.py").write_text("print('hello')")
        (root / "goodbye.py").write_text("print('bye')")

        db = tmp_path / "idx.db"
        idx = FileSearchIndex(db)
        idx.scan(root)

        results = idx.search("hello")
        assert len(results) >= 1
        assert any("hello" in r.basename.lower() for r in results)

    def test_search_prefix_match(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        (root / "test_final_benchmark.py").write_text("def bench(): pass")

        db = tmp_path / "idx.db"
        idx = FileSearchIndex(db)
        idx.scan(root)

        results = idx.search("test final benchmark")
        assert len(results) >= 1
        # The query phrase should appear in the top result
        top = results[0]
        assert "test" in top.basename.lower() or "benchmark" in top.basename.lower()

    def test_search_empty_query(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        (root / "file.txt").write_text("data")

        db = tmp_path / "idx.db"
        idx = FileSearchIndex(db)
        idx.scan(root)

        results = idx.search("")
        assert results == []

    def test_search_no_match(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        (root / "alpha.txt").write_text("hello")

        db = tmp_path / "idx.db"
        idx = FileSearchIndex(db)
        idx.scan(root)

        results = idx.search("xyz_no_match_12345")
        assert results == []

    def test_search_respects_limit(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        for i in range(50):
            (root / f"file_{i:03d}.txt").write_text(f"content {i}")

        db = tmp_path / "idx.db"
        idx = FileSearchIndex(db)
        idx.scan(root)

        results = idx.search("file", limit=5)
        assert len(results) <= 5

    def test_search_incremental_add(self, tmp_path):
        """After adding a file to disk, incremental update picks it up."""
        root = tmp_path / "root"
        root.mkdir()
        (root / "existing.txt").write_text("exists")

        db = tmp_path / "idx.db"
        idx = FileSearchIndex(db)
        idx.scan(root)

        # Add a new file
        (root / "new_file.txt").write_text("new content")
        idx._incremental_update(root, exclude_patterns=[])

        results = idx.search("new_file")
        assert any("new_file" in r.basename for r in results)

    def test_search_incremental_delete(self, tmp_path):
        """After removing a file from disk, incremental update removes it."""
        root = tmp_path / "root"
        root.mkdir()
        (root / "to_delete.txt").write_text("delete me")

        db = tmp_path / "idx.db"
        idx = FileSearchIndex(db)
        idx.scan(root)

        assert len(idx.search("to_delete")) >= 1

        # Remove the file
        (root / "to_delete.txt").unlink()
        idx._incremental_update(root, exclude_patterns=[])

        results = idx.search("to_delete")
        assert len(results) == 0

    def test_search_incremental_modified(self, tmp_path):
        """Modifying a file's mtime triggers an incremental update."""
        root = tmp_path / "root"
        root.mkdir()
        fp = root / "mod_target.txt"
        fp.write_text("v1")

        db = tmp_path / "idx.db"
        idx = FileSearchIndex(db)
        idx.scan(root)

        time.sleep(0.05)
        fp.write_text("v2 updated")
        idx._incremental_update(root, exclude_patterns=[])

        # Should still find it (just verifying no crash / correct re-index)
        results = idx.search("mod_target")
        assert len(results) >= 1


class TestSearchResultDataclass:
    def test_fields_present(self, tmp_path):
        root = tmp_path / "root"
        root.mkdir()
        (root / "sample.txt").write_text("hello")

        db = tmp_path / "idx.db"
        idx = FileSearchIndex(db)
        idx.scan(root)

        results = idx.search("sample")
        assert len(results) >= 1
        r = results[0]
        assert isinstance(r, SearchResult)
        assert r.path
        assert r.basename
        assert r.extension == "txt"
        assert r.size > 0
        assert r.mtime > 0
        assert r.snippet  # may be empty string but must exist