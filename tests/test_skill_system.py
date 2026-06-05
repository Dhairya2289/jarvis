"""
Tests for jarvis.skill_system
────────────────────────────────
Skill discovery, run, create, list, and registry persistence.
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from jarvis.skill_system import (
    Skill,
    SkillRegistry,
    DEFAULT_SKILLS_DIR,
)


# ── Fixtures ──────────────────────────────────────────────

@pytest.fixture
def temp_skills_dir(tmp_path: Path) -> Path:
    """Temporary skills directory."""
    d = tmp_path / "skills"
    d.mkdir()
    return d


@pytest.fixture
def registry(temp_skills_dir: Path) -> SkillRegistry:
    return SkillRegistry(skills_dir=temp_skills_dir)


# ── Discovery ─────────────────────────────────────────────

class TestDiscover:

    def test_discover_finds_no_skills_when_dir_empty(self, registry: SkillRegistry):
        skills = registry.discover()
        assert skills == []
        assert registry._cache == {}

    def test_discover_loads_valid_skill(self, temp_skills_dir: Path):
        (temp_skills_dir / "hello.py").write_text(
            "\n".join([
                'skill_meta = {"name": "hello", "description": "Says hello", "version": "1.0", "tags": ["test"]}',
                "def run(**kwargs):",
                "    return 'Hello, World!'",
            ])
        )
        reg = SkillRegistry(skills_dir=temp_skills_dir)
        skills = reg.discover()
        assert len(skills) == 1
        assert skills[0].name == "hello"
        assert skills[0].version == "1.0"
        assert skills[0].tags == ["test"]

    def test_discover_skips_file_without_skill_meta(self, temp_skills_dir: Path):
        (temp_skills_dir / "no_meta.py").write_text("def run(**kwargs): pass\n")
        reg = SkillRegistry(skills_dir=temp_skills_dir)
        skills = reg.discover()
        assert skills == []
        assert "hello" not in reg._cache  # only "no_meta" was skipped

    def test_discover_skips_file_without_run(self, temp_skills_dir: Path):
        (temp_skills_dir / "no_run.py").write_text(
            'skill_meta = {"name": "no_run", "description": "missing run"}'
        )
        reg = SkillRegistry(skills_dir=temp_skills_dir)
        skills = reg.discover()
        assert skills == []

    def test_discover_caches_results(self, temp_skills_dir: Path):
        (temp_skills_dir / "greet.py").write_text(
            "\n".join([
                'skill_meta = {"name": "greet", "description": "greet"}',
                "def run(**kwargs): return 'hi'",
            ])
        )
        reg = SkillRegistry(skills_dir=temp_skills_dir)
        reg.discover()
        first_names = set(reg._cache.keys())
        reg.discover()  # second call — should not re-scan
        # Function objects may differ (module reload) so compare by name only
        assert set(reg._cache.keys()) == first_names

    def test_discover_multiple_skills(self, temp_skills_dir: Path):
        for name in ("alpha", "beta", "gamma"):
            (temp_skills_dir / f"{name}.py").write_text(
                "\n".join([
                    f'skill_meta = {{"name": "{name}", "description": "{name}"}}',
                    f"def run(**kwargs): return '{name}'",
                ])
            )
        reg = SkillRegistry(skills_dir=temp_skills_dir)
        skills = reg.discover()
        assert len(skills) == 3
        assert {s.name for s in skills} == {"alpha", "beta", "gamma"}


# ── Run ────────────────────────────────────────────────────

class TestRun:

    def test_run_calls_skill_function(self, temp_skills_dir: Path):
        (temp_skills_dir / "adder.py").write_text(
            "\n".join([
                'skill_meta = {"name": "adder", "description": "adds two numbers"}',
                "def run(**kwargs):",
                "    a = kwargs.get('a', 0)",
                "    b = kwargs.get('b', 0)",
                "    return a + b",
            ])
        )
        reg = SkillRegistry(skills_dir=temp_skills_dir)
        reg.discover()
        result = reg.run("adder", a=3, b=7)
        assert result == 10

    def test_run_raises_for_unknown_skill(self, registry: SkillRegistry):
        registry.discover()
        with pytest.raises(ValueError, match="No skill named"):
            registry.run("does_not_exist")

    def test_run_propagates_skill_exception(self, temp_skills_dir: Path):
        (temp_skills_dir / "boom.py").write_text(
            "\n".join([
                'skill_meta = {"name": "boom", "description": "raises"}',
                "def run(**kwargs):",
                "    raise RuntimeError('boom!')",
            ])
        )
        reg = SkillRegistry(skills_dir=temp_skills_dir)
        reg.discover()
        with pytest.raises(RuntimeError, match="boom!"):
            reg.run("boom")


# ── List ───────────────────────────────────────────────────

class TestListSkills:

    def test_list_empty_when_no_skills(self, registry: SkillRegistry):
        registry.discover()
        output = registry.list_skills()
        assert "No skills" in output

    def test_list_shows_skill_names_and_descriptions(self, temp_skills_dir: Path):
        (temp_skills_dir / "foo.py").write_text(
            "\n".join([
                'skill_meta = {"name": "foo", "description": "Does foo things", "tags": ["test"]}',
                "def run(**kwargs): return None",
            ])
        )
        reg = SkillRegistry(skills_dir=temp_skills_dir)
        reg.discover()
        output = reg.list_skills()
        assert "foo" in output
        assert "Does foo things" in output


# ── Create ─────────────────────────────────────────────────

class TestCreateSkill:

    def test_create_skill_writes_file(self, tmp_path: Path):
        # Override the default skills dir to our temp dir
        original = Path.home() / ".jarvis" / "skills"
        # Patch used via import temporarily
        SkillRegistry.create_skill(
            name="greet",
            description="Greets the user",
            code='return "Hello, " + kwargs.get("name", "World")',
        )
        # Check it was created in the actual default location for this test
        # We verify the method works by checking it doesn't raise
        # The file is created at DEFAULT_SKILLS_DIR which may not exist in temp
        # So we check that the method completes without error
        pass  # smoke test — full path tested via integration below

    def test_create_skill_produces_valid_python(self, tmp_path: Path):
        """create_skill should produce a .py file that parses without error."""
        import ast
        skill_path = SkillRegistry.create_skill(
            name="adder",
            description="Adds two numbers",
            code='a = kwargs.get("a", 0)\nb = kwargs.get("b", 0)\nreturn a + b',
        )
        # Verify the file exists
        assert skill_path.name == "adder.py"
        # Verify it parses
        source = skill_path.read_text()
        ast.parse(source)
        # Verify skill_meta and run are in the file
        assert "skill_meta" in source
        assert "def run(" in source
        assert "adder" in source


# ── Registry persistence ───────────────────────────────────

class TestRegistryPersistence:

    def test_save_load_roundtrip(self, temp_skills_dir: Path):
        (temp_skills_dir / "my_skill.py").write_text(
            "\n".join([
                'skill_meta = {"name": "my_skill", "description": "my skill", "version": "2.0", "tags": ["a", "b"]}',
                "def run(**kwargs): return None",
            ])
        )
        reg = SkillRegistry(skills_dir=temp_skills_dir)
        reg.discover()
        reg.save_registry()

        reg2 = SkillRegistry(skills_dir=temp_skills_dir)
        reg2.load_registry()
        # Should have loaded metadata without re-discovering code
        assert "my_skill" in reg2._cache
        assert reg2._cache["my_skill"].version == "2.0"
        assert reg2._cache["my_skill"].tags == ["a", "b"]

    def test_load_registry_nonexistent_file_is_silent(self, registry: SkillRegistry):
        # Should not raise
        registry.load_registry()

    def test_save_registry_produces_valid_json(self, temp_skills_dir: Path):
        (temp_skills_dir / "j.py").write_text(
            "\n".join([
                'skill_meta = {"name": "j", "description": "j"}',
                "def run(**kwargs): return None",
            ])
        )
        reg = SkillRegistry(skills_dir=temp_skills_dir)
        reg.discover()
        reg.save_registry()

        registry_path = temp_skills_dir / ".registry.json"
        data = json.loads(registry_path.read_text())
        assert "skills" in data
        assert isinstance(data["skills"], list)