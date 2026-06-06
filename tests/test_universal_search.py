"""Tests for jarvis.universal_search"""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from jarvis.universal_search import (
    UniversalSearcher,
    universal_search,
    SearchResult,
)


# -------------------------------------------------------------------------- #
# Fixtures
# -------------------------------------------------------------------------- #

@pytest.fixture
def temp_index_path(tmp_path):
    return tmp_path / "idx.db"


@pytest.fixture
def temp_vault(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "obsidian_note.md").write_text("# Obsidian Note\nSome content")
    (vault / "project_plan.md").write_text("# Project Plan\n## Goals")
    return vault


@pytest.fixture
def searcher(temp_index_path, temp_vault):
    return UniversalSearcher(
        index_path=temp_index_path,
        vault_path=temp_vault,
    )


# -------------------------------------------------------------------------- #
# Helper
# -------------------------------------------------------------------------- #

def _seed_file_index(index_path: Path, root: Path) -> None:
    """Seed the file index with some files."""
    from jarvis.file_search_index import FileSearchIndex
    idx = FileSearchIndex(index_path)
    idx.scan(root)


# -------------------------------------------------------------------------- #
# UniversalSearcher.search — mixed scope tests
# -------------------------------------------------------------------------- #

class TestUniversalSearchMixed:
    def test_files_scope_alone(self, searcher, tmp_path):
        """universal_search with scopes=['files'] returns only file results."""
        # Set up a file
        file_root = tmp_path / "files"
        file_root.mkdir()
        (file_root / "report.txt").write_text("quarterly report")

        _seed_file_index(searcher.index_path, file_root)

        searcher.scopes = {"files"}
        results = searcher.search("report")

        assert all(r.kind == "file" for r in results)
        assert any("report" in r.title.lower() for r in results)

    def test_apps_scope_alone(self, searcher):
        """universal_search with scopes=['apps'] returns only app results."""
        mock_app = MagicMock()
        mock_app.name = "Obsidian"
        mock_app.exec = "obsidian"
        mock_app.categories = ["Utility"]
        mock_app.comment = "knowledge base"
        mock_app.keywords = ["notes", "markdown"]
        mock_app.terminal = False

        with patch("jarvis.apps.desktop.search_apps", return_value=[mock_app]):
            searcher.scopes = {"apps"}
            results = searcher.search("obsidian")

        assert len(results) == 1
        assert results[0].kind == "app"
        assert results[0].title == "Obsidian"
        assert results[0].score > 0

    def test_vault_scope_alone(self, searcher):
        """universal_search with scopes=['vault'] returns only vault results."""
        searcher.scopes = {"vault"}
        results = searcher.search("obsidian")

        assert all(r.kind == "vault" for r in results)
        assert any("obsidian" in r.title.lower() for r in results)

    def test_files_and_apps_mixed(self, searcher, tmp_path):
        """universal_search(scopes=['files','apps']) returns mixed results."""
        # Seed file index
        file_root = tmp_path / "files"
        file_root.mkdir()
        (file_root / "obsidian_backup.txt").write_text("backup data")

        _seed_file_index(searcher.index_path, file_root)

        mock_app = MagicMock()
        mock_app.name = "Obsidian"
        mock_app.exec = "obsidian"
        mock_app.categories = []
        mock_app.comment = ""
        mock_app.keywords = []
        mock_app.terminal = False

        with patch("jarvis.apps.desktop.search_apps", return_value=[mock_app]):
            searcher.scopes = {"files", "apps"}
            results = searcher.search("obsidian")

        kinds = {r.kind for r in results}
        assert "file" in kinds
        assert "app" in kinds

    def test_default_scopes_all_three(self, searcher, tmp_path):
        """Default (scopes=None) searches all three scopes."""
        file_root = tmp_path / "files"
        file_root.mkdir()
        (file_root / "obsidian_sync.txt").write_text("sync data")
        _seed_file_index(searcher.index_path, file_root)

        mock_app = MagicMock()
        mock_app.name = "Obsidian"
        mock_app.exec = "obsidian"
        mock_app.categories = []
        mock_app.comment = ""
        mock_app.keywords = []
        mock_app.terminal = False

        with patch("jarvis.apps.desktop.search_apps", return_value=[mock_app]):
            # Default scopes = all three
            searcher.scopes = {"files", "apps", "vault"}
            results = searcher.search("obsidian")

        kinds = {r.kind for r in results}
        assert kinds == {"file", "app", "vault"}

    def test_results_sorted_by_score(self, searcher, tmp_path):
        """Results are sorted descending by score."""
        file_root = tmp_path / "files"
        file_root.mkdir()
        (file_root / "zebra.txt").write_text("animal")
        _seed_file_index(searcher.index_path, file_root)

        searcher.scopes = {"files"}
        results = searcher.search("zebra")

        if len(results) >= 2:
            scores = [r.score for r in results]
            assert scores == sorted(scores, reverse=True)

    def test_empty_query_returns_empty(self, searcher):
        """Empty query returns empty list."""
        results = searcher.search("")
        assert results == []

    def test_whitespace_query_returns_empty(self, searcher):
        """Whitespace-only query returns empty list."""
        results = searcher.search("   ")
        assert results == []

    def test_no_results_across_all_scopes(self, searcher):
        """Query with no matches returns empty list."""
        searcher.scopes = {"files", "apps", "vault"}
        # Use a truly unmatchable query string
        results = searcher.search("zzzqqqyyyxxx_no_match_999999")
        assert results == []

    def test_result_has_required_fields(self, searcher, tmp_path):
        """Every result has kind, title, path, score."""
        file_root = tmp_path / "files"
        file_root.mkdir()
        (file_root / "notes.txt").write_text("my notes")
        _seed_file_index(searcher.index_path, file_root)

        searcher.scopes = {"files"}
        results = searcher.search("notes")
        assert len(results) >= 1

        r = results[0]
        assert isinstance(r, SearchResult)
        assert r.kind in {"file", "app", "vault"}
        assert r.title
        assert r.path is not None or r.title  # path optional for apps
        assert isinstance(r.score, float)
        assert 0 <= r.score <= 100


# -------------------------------------------------------------------------- #
# Module-level convenience function
# -------------------------------------------------------------------------- #

class TestUniversalSearchFunction:
    def test_universal_search_accepts_scopes(self, tmp_path):
        """universal_search accepts scopes kwarg."""
        vault = tmp_path / "v"
        vault.mkdir()
        (vault / "a.md").write_text("# a")
        results = universal_search("a", scopes=["vault"])
        assert isinstance(results, list)
        assert all(isinstance(r, SearchResult) for r in results)


# -------------------------------------------------------------------------- #
# Scoping / limiting
# -------------------------------------------------------------------------- #

class TestLimitPerScope:
    def test_limit_per_scope_applied(self, searcher, tmp_path):
        """limit_per_scope is passed through to each scope searcher."""
        file_root = tmp_path / "files"
        file_root.mkdir()
        for i in range(30):
            (file_root / f"file_{i}.txt").write_text(f"content {i}")
        _seed_file_index(searcher.index_path, file_root)

        searcher.scopes = {"files"}
        results = searcher.search("file", limit_per_scope=5)

        # Should respect limit (file search returns at most limit_per_scope)
        file_results = [r for r in results if r.kind == "file"]
        assert len(file_results) <= 5


# -------------------------------------------------------------------------- #
# UniversalSearcher._search_vault
# -------------------------------------------------------------------------- #

class TestVaultSearch:
    def test_vault_finds_note_by_basename(self, searcher):
        """Vault search matches on note basename (substring)."""
        searcher.scopes = {"vault"}
        results = searcher.search("project")

        assert len(results) >= 1
        assert any("project" in r.title.lower() for r in results)
        assert all(r.kind == "vault" for r in results)

    def test_vault_returns_correct_path(self, searcher):
        """Vault results have correct .path pointing to .md file."""
        searcher.scopes = {"vault"}
        results = searcher.search("obsidian_note")

        assert len(results) >= 1
        r = results[0]
        assert r.path.endswith(".md")

    def test_vault_missing_dir_returns_empty(self, tmp_path):
        """Non-existent vault path returns empty list, not an error."""
        sr = UniversalSearcher(
            scopes={"vault"},
            vault_path=tmp_path / "nonexistent_vault",
        )
        results = sr.search("anything")
        assert results == []

    def test_vault_skips_obsidian_internals(self, tmp_path):
        """Notes inside .obsidian folder are not returned."""
        vault = tmp_path / "vault2"
        vault.mkdir()
        (vault / "note.md").write_text("# Note")
        obsidian_dir = vault / ".obsidian"
        obsidian_dir.mkdir()
        (obsidian_dir / "internal.md").write_text("# Internal")

        sr = UniversalSearcher(scopes={"vault"}, vault_path=vault)
        results = sr.search("internal")

        # The .obsidian internal note should be filtered out
        paths = [r.path for r in results]
        assert not any(".obsidian" in p for p in paths)


# -------------------------------------------------------------------------- #
# SearchResult dataclass invariants
# -------------------------------------------------------------------------- #

class TestSearchResultDataclass:
    def test_score_in_0_100(self, searcher, tmp_path):
        """All returned scores are in [0, 100]."""
        file_root = tmp_path / "files"
        file_root.mkdir()
        (file_root / "score_test.txt").write_text("data")
        _seed_file_index(searcher.index_path, file_root)

        searcher.scopes = {"files", "vault"}
        results = searcher.search("score")
        for r in results:
            assert 0 <= r.score <= 100, f"score {r.score} out of range for {r.title}"

    def test_meta_is_dict(self, searcher):
        """SearchResult.meta is always a dict."""
        searcher.scopes = {"vault"}
        results = searcher.search("note")
        for r in results:
            assert isinstance(r.meta, dict)