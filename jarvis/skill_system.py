"""
Skill System — JARVIS V3 Dynamic Skill Registry
────────────────────────────────────────────────
Discovers, loads, and runs self-contained Python skill modules
from ~/.jarvis/skills/.  Each skill is a .py file with a
`skill_meta` dict and a `run()` function.
"""

from __future__ import annotations

import importlib.util
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

_LOG = logging.getLogger(__name__)

# ── Defaults ──────────────────────────────────────────────

DEFAULT_SKILLS_DIR = Path.home() / ".jarvis" / "skills"


# ── Public Types ──────────────────────────────────────────

@dataclass
class Skill:
    """Metadata + callable for a single skill."""
    name: str
    description: str
    func: Callable[..., Any]
    version: str = "1.0"
    tags: list[str] = field(default_factory=list)
    source_file: Path | None = None

    def __hash__(self) -> int:
        return hash(self.name)


# ── SkillRegistry ─────────────────────────────────────────

class SkillRegistry:
    """
    Discovers Python skill modules from a directory and provides
    a run / list / create interface.

    Skills are cached after the first call to :meth:`discover`.
    """

    def __init__(self, skills_dir: Path | None = None) -> None:
        self.skills_dir = (skills_dir or DEFAULT_SKILLS_DIR).expanduser().resolve()
        self._cache: dict[str, Skill] = {}
        self._discovered = False

    # ── Discovery ──────────────────────────────────────────

    def discover(self) -> list[Skill]:
        """
        Scan ``skills_dir`` for ``.py`` files, load each one, and
        return a list of :class:`Skill` instances.

        Files that do not expose both a ``skill_meta`` dict and a
        ``run`` callable are skipped with a logged warning.
        """
        self._cache.clear()
        self._discovered = True

        if not self.skills_dir.is_dir():
            _LOG.warning("Skills directory does not exist: %s", self.skills_dir)
            return []

        skill_files = sorted(self.skills_dir.glob("*.py"))
        discovered: list[Skill] = []

        for path in skill_files:
            try:
                skill = self._load_skill_file(path)
                if skill is not None:
                    self._cache[skill.name] = skill
                    discovered.append(skill)
            except Exception as exc:
                _LOG.warning("Failed to load skill file %s: %s", path, exc)

        _LOG.info("Discovered %d skills in %s", len(discovered), self.skills_dir)
        return discovered

    def _load_skill_file(self, path: Path) -> Skill | None:
        """Load a single skill file and return a Skill instance, or None."""
        # Use importlib to load the module without side-effects on sys.path
        spec = importlib.util.spec_from_file_location(path.stem, path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore

        meta: dict[str, Any] | None = getattr(module, "skill_meta", None)
        if not isinstance(meta, dict):
            _LOG.warning("Skill file %s is missing 'skill_meta' dict — skipped", path)
            return None

        run_func: Callable[..., Any] | None = getattr(module, "run", None)
        if not callable(run_func):
            _LOG.warning("Skill file %s is missing callable 'run' — skipped", path)
            return None

        return Skill(
            name=meta.get("name", path.stem),
            description=meta.get("description", ""),
            func=run_func,
            version=meta.get("version", "1.0"),
            tags=meta.get("tags", []),
            source_file=path,
        )

    # ── Access ─────────────────────────────────────────────

    def _ensure_discovered(self) -> None:
        if not self._discovered:
            self.discover()

    def run(self, name: str, **kwargs: Any) -> Any:
        """
        Find skill ``name`` and invoke its ``run(**kwargs)`` function.

        Raises:
            ValueError: if the skill is not found.
        """
        self._ensure_discovered()
        skill = self._cache.get(name)
        if skill is None:
            raise ValueError(f"No skill named {name!r}")
        try:
            return skill.func(**kwargs)
        except Exception as exc:
            _LOG.error("Skill %s raised: %s", name, exc)
            raise

    def list_skills(self) -> str:
        """
        Return a human-readable list of all discovered skills.
        """
        self._ensure_discovered()
        if not self._cache:
            return "No skills registered."

        lines = ["Registered skills:"]
        for skill in sorted(self._cache.values(), key=lambda s: s.name):
            tags = ", ".join(f"#{t}" for t in skill.tags) if skill.tags else ""
            lines.append(
                f"  • {skill.name} v{skill.version} — {skill.description} {tags}"
            )
        return "\n".join(lines)

    # ── Create ─────────────────────────────────────────────

    @staticmethod
    def create_skill(name: str, description: str, code: str) -> Path:
        """
        Write a new skill file to the default skills directory and
        return its path.

        Args:
            name: unique skill name (used as filename stem).
            description: one-line description for ``skill_meta``.
            code: the body of the ``run()`` function (not including the
                  def line — it is prepended automatically).

        Returns:
            Path to the created file.

        The file is written only to the filesystem; caller should call
        :meth:`discover` afterwards to register it.
        """
        filename = f"{name}.py"
        file_path = DEFAULT_SKILLS_DIR / filename

        body = "\n".join([
            f"# Auto-generated skill: {name}",
            f"# {description}",
            "",
            "from __future__ import annotations",
            "",
            "skill_meta = {",
            f'    "name": "{name}",',
            f'    "description": "{description}",',
            '    "version": "1.0",',
            '    "tags": [],',
            "}",
            "",
            "def run(**kwargs):",
        ] + [
            "    " + line for line in code.strip().split("\n")
        ]) + "\n"

        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(body)
        _LOG.info("Created skill file: %s", file_path)
        return file_path

    # ── Registry persistence ───────────────────────────────

    def save_registry(self) -> None:
        """
        Write a JSON manifest of all discovered skills to
        ``{skills_dir}/.registry.json``.
        """
        self._ensure_discovered()
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        registry_path = self.skills_dir / ".registry.json"
        entries = [
            {
                "name": s.name,
                "description": s.description,
                "version": s.version,
                "tags": s.tags,
                "source_file": str(s.source_file) if s.source_file else None,
            }
            for s in self._cache.values()
        ]
        registry_path.write_text(json.dumps({"skills": entries}, indent=2))
        _LOG.debug("Registry saved to %s", registry_path)

    def load_registry(self) -> None:
        """
        Load a previously saved registry from
        ``{skills_dir}/.registry.json`` and merge into the cache.

        Does **not** reload skill code; call :meth:`discover` to reload.
        """
        registry_path = self.skills_dir / ".registry.json"
        if not registry_path.is_file():
            _LOG.debug("No registry file at %s", registry_path)
            return
        try:
            data = json.loads(registry_path.read_text())
        except Exception as exc:
            _LOG.warning("Failed to load registry %s: %s", registry_path, exc)
            return
        entries: list[dict[str, Any]] = data.get("skills", [])
        for entry in entries:
            # Merge only metadata — func must come from discover()
            if entry["name"] not in self._cache:
                self._cache[entry["name"]] = Skill(
                    name=entry["name"],
                    description=entry.get("description", ""),
                    func=lambda **_: None,  # placeholder until discover() reloads
                    version=entry.get("version", "1.0"),
                    tags=entry.get("tags", []),
                    source_file=Path(entry["source_file"]) if entry.get("source_file") else None,
                )
        _LOG.debug("Loaded %d entries from registry", len(entries))


