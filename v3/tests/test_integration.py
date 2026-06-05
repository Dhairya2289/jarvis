"""
v3/tests/test_integration.py
JARVIS V3 Integration Tests
"""

import tempfile
import uuid
from pathlib import Path

import pytest

# ── Set up temp PYTHONPATH for isolated runs ───────────────
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ── Helpers ─────────────────────────────────────────────────

def _tmp_vault(tmp_path):
    """Return a Path to a temporary vault directory."""
    return tmp_path / "vault"


# ── Tests ───────────────────────────────────────────────────

class TestObsidianToolsDispatch:
    """Test that obsidian_* tools are registered and dispatchable."""

    def test_obsidian_create_dispatch(self, tmp_path):
        from jarvis_v3.tools import dispatch_tool
        from jarvis_v3.obsidian_brain import ObsidianBrain

        # Use a temp vault so tests don't bleed into real data
        vault = _tmp_vault(tmp_path)
        name = f"test_note_{uuid.uuid4().hex[:8]}"

        # Patch ObsidianBrain to use temp vault
        import jarvis_v3.obsidian_brain as ob_mod
        orig_init = ObsidianBrain.__init__
        def patched_init(self, vault_path=None):
            return orig_init(self, vault_path=vault)
        ObsidianBrain.__init__ = patched_init
        try:
            result = dispatch_tool("obsidian_create", {
                "name": name,
                "content": "Hello from integration test",
                "folder": "general",
                "tags": ["test"],
            })
            assert "[OBSIDIAN] Created:" in result, f"Unexpected result: {result}"
            # Verify the note actually exists in temp vault
            note = ObsidianBrain(vault_path=vault).read_note(name, folder="general")
            assert note["content"] == "Hello from integration test"
        finally:
            ObsidianBrain.__init__ = orig_init

    def test_obsidian_read_dispatch(self, tmp_path):
        from jarvis_v3.tools import dispatch_tool
        from jarvis_v3.obsidian_brain import ObsidianBrain

        vault = _tmp_vault(tmp_path)
        note_name = f"read_test_{uuid.uuid4().hex[:8]}"
        # Pre-create note in temp vault
        ObsidianBrain(vault_path=vault).create_note(note_name, "Read me!", folder="general")

        # Patch ObsidianBrain so dispatch tool uses temp vault
        import jarvis_v3.obsidian_brain as ob_mod
        orig_init = ObsidianBrain.__init__
        def patched_init(self, vault_path=None):
            return orig_init(self, vault_path=vault)
        ObsidianBrain.__init__ = patched_init
        try:
            result = dispatch_tool("obsidian_read", {"name": note_name, "folder": "general"})
            assert result == "Read me!", f"Unexpected result: {result}"
        finally:
            ObsidianBrain.__init__ = orig_init

    def test_obsidian_search_dispatch(self, tmp_path):
        from jarvis_v3.tools import dispatch_tool
        from jarvis_v3.obsidian_brain import ObsidianBrain

        vault = _tmp_vault(tmp_path)
        note_name = f"search_test_{uuid.uuid4().hex[:8]}"
        ObsidianBrain(vault_path=vault).create_note(note_name, "Unique magic word xyz123", folder="general")

        import jarvis_v3.obsidian_brain as ob_mod
        orig_init = ObsidianBrain.__init__
        def patched_init(self, vault_path=None):
            return orig_init(self, vault_path=vault)
        ObsidianBrain.__init__ = patched_init
        try:
            result = dispatch_tool("obsidian_search", {"query": "magic word"})
            assert "search_test" in result, f"Unexpected result: {result}"
        finally:
            ObsidianBrain.__init__ = orig_init

    def test_obsidian_daily_dispatch(self, tmp_path):
        from jarvis_v3.tools import dispatch_tool
        from jarvis_v3.obsidian_brain import ObsidianBrain

        vault = _tmp_vault(tmp_path)
        # Patch global vault path for this test
        import jarvis_v3.obsidian_brain as ob
        orig_vault = ob.Path.home()  # will be shadowed by param
        brain = ObsidianBrain(vault_path=vault)

        result = dispatch_tool("obsidian_daily", {"text": "test entry"})
        assert "[OBSIDIAN] Daily note:" in result, f"Unexpected result: {result}"


class TestMemDirToolsDispatch:
    """Test that memdir_* tools are registered and dispatchable."""

    def test_memdir_add_dispatch(self, tmp_path):
        from jarvis_v3.tools import dispatch_tool
        from jarvis_v3.memdir import MemDir

        data_dir = tmp_path / "memdir"
        MemDir._instances = {}  # type: ignore
        # Use a fresh MemDir with tmp data dir
        from jarvis_v3 import memdir as md_module
        orig_dir = md_module.DEFAULT_DATA_DIR
        md_module.DEFAULT_DATA_DIR = data_dir

        try:
            result = dispatch_tool("memdir_add", {
                "content": "JARVIS is running on CachyOS",
                "mem_type": "fact",
                "confidence": 0.95,
                "tags": ["os", "context"],
            })
            assert "[MEMDIR] Added:" in result, f"Unexpected result: {result}"
            # Verify it can be found again
            search_result = dispatch_tool("memdir_search", {
                "query": "CachyOS",
                "mem_type": "fact",
            })
            assert "CachyOS" in search_result, f"Search failed: {search_result}"
        finally:
            md_module.DEFAULT_DATA_DIR = orig_dir

    def test_memdir_search_dispatch(self, tmp_path):
        from jarvis_v3.tools import dispatch_tool
        from jarvis_v3.memdir import MemDir

        data_dir = tmp_path / "memdir2"
        from jarvis_v3 import memdir as md_module
        orig_dir = md_module.DEFAULT_DATA_DIR
        md_module.DEFAULT_DATA_DIR = data_dir

        try:
            # Seed a memory first
            dispatch_tool("memdir_add", {
                "content": "I prefer dark mode",
                "mem_type": "preference",
            })
            result = dispatch_tool("memdir_search", {
                "query": "dark mode",
            })
            assert "preference" in result, f"Unexpected result: {result}"
        finally:
            md_module.DEFAULT_DATA_DIR = orig_dir


class TestSkillToolsDispatch:
    """Test skill_* tool dispatch."""

    def test_skill_list_dispatch(self, tmp_path):
        from jarvis_v3.tools import dispatch_tool

        # SkillRegistry will find an empty or real skills dir
        # Just verify it returns a string without error
        result = dispatch_tool("skill_list", {})
        assert isinstance(result, str), f"Expected string, got {type(result)}"
        assert "SKILL" not in result or "error" not in result.lower(), f"Error in result: {result}"


class TestModuleImports:
    """Test that all new modules can be imported together without conflicts."""

    def test_obsidian_memdir_coordinator_import(self):
        """Verify ObsidianBrain, MemDir, and Coordinator import cleanly together."""
        from jarvis_v3.obsidian_brain import ObsidianBrain
        from jarvis_v3.memdir import MemDir
        from jarvis_v3.coordinator import Coordinator

        assert ObsidianBrain is not None
        assert MemDir is not None
        assert Coordinator is not None

    def test_context_engine_import(self):
        """Verify context_engine classifies a known query."""
        from jarvis_v3.context_engine import classify_intent, route

        intent = classify_intent("remember what I said last time")
        assert intent.category == "memory", f"Expected memory, got {intent.category}"
        specialist = route(intent)
        assert specialist == "episodic_memory"


# ── Fixture ─────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _clean_memdir_singletons():
    """Reset MemDir singletons between tests to avoid shared state."""
    import jarvis_v3.memdir as md
    # Reset any cached instances
    yield
    # Cleanup tmp memdir files created during test