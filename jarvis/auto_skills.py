"""JARVIS Auto-Skill Detector

Watches agent tool usage for repeated patterns and auto-creates skills
when a pattern crosses a confidence threshold.

Inspired by Hermes agent/skill_creation.py.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jarvis.config import BASE_DIR

_log = logging.getLogger(__name__)

PATTERNS_FILE: Path = BASE_DIR / "training" / "tool_patterns.json"
SKILL_THRESHOLD: int = 3
DECAY_HOURS: float = 24.0


@dataclass
class ToolPattern:
    """A detected pattern of tool calls."""
    tool_name: str
    arg_signature: str  # canonical arg keys
    frequency: int = 1
    last_seen: float = field(default_factory=time.time)
    examples: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "arg_signature": self.arg_signature,
            "frequency": self.frequency,
            "last_seen": self.last_seen,
            "examples": self.examples[:3],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolPattern:
        return cls(
            tool_name=data["tool_name"],
            arg_signature=data["arg_signature"],
            frequency=data.get("frequency", 1),
            last_seen=data.get("last_seen", time.time()),
            examples=data.get("examples", []),
        )


def _canonical_args(args: dict[str, Any]) -> str:
    """Generate a canonical string of arg names."""
    return ",".join(sorted(str(k) for k in args.keys()))


def _pattern_id(tool_name: str, arg_signature: str) -> str:
    return hashlib.sha256(f"{tool_name}:{arg_signature}".encode()).hexdigest()[:12]


class AutoSkillDetector:
    """Watches tool usage, clusters patterns, auto-creates skills."""

    def __init__(self, *, threshold: int = SKILL_THRESHOLD, decay_hours: float = DECAY_HOURS) -> None:
        self.threshold = threshold
        self.decay_hours = decay_hours
        self.patterns: dict[str, ToolPattern] = self._load()

    # ------------------------------------------------------------------
    #  Persistence
    # ------------------------------------------------------------------
    def _load(self) -> dict[str, ToolPattern]:
        if not PATTERNS_FILE.exists():
            return {}
        try:
            data = json.loads(PATTERNS_FILE.read_text(encoding="utf-8"))
            return {k: ToolPattern.from_dict(v) for k, v in data.items()}
        except Exception as exc:
            _log.error("Failed to load patterns: %s", exc)
            return {}

    def _save(self) -> None:
        PATTERNS_FILE.parent.mkdir(parents=True, exist_ok=True)
        PATTERNS_FILE.write_text(
            json.dumps(
                {k: v.to_dict() for k, v in self.patterns.items()},
                indent=2,
            ),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    #  Observation
    # ------------------------------------------------------------------
    def observe(self, tool_name: str, args: dict[str, Any]) -> str | None:
        """Record a tool call. Returns the skill name if a new skill was created."""
        sig = _canonical_args(args)
        pid = _pattern_id(tool_name, sig)
        now = time.time()

        if pid in self.patterns:
            pat = self.patterns[pid]
            pat.frequency += 1
            pat.last_seen = now
            if len(pat.examples) < 5:
                pat.examples.append({"args": args, "ts": now})
        else:
            self.patterns[pid] = ToolPattern(
                tool_name=tool_name,
                arg_signature=sig,
                frequency=1,
                last_seen=now,
                examples=[{"args": args, "ts": now}],
            )

        self._save()
        _log.debug("Observed %s (%s) freq=%d", tool_name, sig, self.patterns[pid].frequency)

        if self.patterns[pid].frequency >= self.threshold:
            return self._maybe_create_skill(pid)
        return None

    # ------------------------------------------------------------------
    #  Skill creation
    # ------------------------------------------------------------------
    def _maybe_create_skill(self, pid: str) -> str | None:
        """Create a new skill for a mature pattern if one doesn't exist yet."""
        from jarvis.skill_system import SkillRegistry

        pat = self.patterns[pid]
        skill_name = f"auto_{pat.tool_name}_{pid[:6]}"

        registry = SkillRegistry()
        registry.discover()
        if skill_name in [s.name for s in registry._skills.values()]:
            return None  # already exists

        # Build skill code from most common arg pattern
        common_args = pat.examples[0]["args"] if pat.examples else {}
        arg_str = ", ".join(f"{k}={repr(v)}" for k, v in common_args.items())
        code = f"""# Auto-generated skill: {skill_name}
# Pattern: {pat.tool_name}({pat.arg_signature})
# Frequency: {pat.frequency}

skill_meta = {{
    "name": {repr(skill_name)},
    "description": "Auto-generated skill for {pat.tool_name}.",
    "version": "1.0",
    "tags": ["auto", {repr(pat.tool_name)}],
}}

def run(**kwargs):
    from jarvis.tools import dispatch_tool
    return dispatch_tool({repr(pat.tool_name)}, kwargs)
"""
        try:
            from jarvis.obsidian_brain import ObsidianBrain
            ObsidianBrain().create_note(
                name=f"skill_{skill_name}",
                content=code,
                folder="skills",
                tags=["auto-skill", pat.tool_name],
                metadata={"pattern_id": pid, "frequency": pat.frequency},
            )
        except Exception:
            pass

        _log.info("Auto-created skill: %s (pattern=%s, freq=%d)", skill_name, pid, pat.frequency)
        return skill_name

    # ------------------------------------------------------------------
    #  Review
    # ------------------------------------------------------------------
    def review(self) -> str:
        """Return a human-readable summary of detected patterns."""
        lines = ["# Auto-Skill Patterns"]
        for pid, pat in sorted(self.patterns.items(), key=lambda x: -x[1].frequency):
            status = "✅ skill" if pat.frequency >= self.threshold else "⏳ watching"
            lines.append(
                f"- {status} `{pat.tool_name}({pat.arg_signature})` — freq={pat.frequency}"
            )
        return "\n".join(lines)

    def prune(self, max_age_hours: float | None = None) -> int:
        """Remove old patterns. Returns count removed."""
        cutoff = time.time() - (max_age_hours or self.decay_hours) * 3600
        before = len(self.patterns)
        self.patterns = {k: v for k, v in self.patterns.items() if v.last_seen > cutoff}
        self._save()
        removed = before - len(self.patterns)
        _log.info("Pruned %d old patterns", removed)
        return removed


__all__ = ["AutoSkillDetector", "ToolPattern"]
