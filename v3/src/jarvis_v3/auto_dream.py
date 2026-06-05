"""JARVIS AutoDream — Background Memory Consolidation

Inspired by Claude Code's autoDream system (TypeScript).
Reimplemented in Python for JARVIS.

Fires as a background subagent when:
  1. Time gate: hours since last consolidation >= MIN_HOURS
  2. Session gate: new sessions accumulated >= MIN_SESSIONS
  3. Lock gate: no other process mid-consolidation

"""
from __future__ import annotations

import fcntl
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Final

from jarvis_v3.config import BASE_DIR

_log = logging.getLogger(__name__)

MIN_HOURS: Final[int] = 24
MIN_SESSIONS: Final[int] = 5
SCAN_INTERVAL_S: Final[int] = 600
LOCK_FILE: Final[Path] = BASE_DIR / ".dream.lock"
STATE_FILE: Final[Path] = BASE_DIR / ".dream_state.json"
MEMORY_FILE: Final[Path] = Path.home() / ".jarvis" / "obsidian" / "memory" / "consolidated_latest.md"


def _read_state() -> dict[str, str]:
    if not STATE_FILE.exists():
        return {"last_consolidated_at": "1970-01-01T00:00:00"}
    try:
        import json
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        _log.warning("Could not read dream state: %s", exc)
        return {"last_consolidated_at": "1970-01-01T00:00:00"}


def _write_state(state: dict[str, str]) -> None:
    try:
        import json
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception as exc:
        _log.error("Could not write dream state: %s", exc)


def _acquire_lock() -> bool:
    """Try to acquire the consolidation file lock."""
    try:
        LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        fd = open(LOCK_FILE, "w")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except (OSError, IOError):
        return False


def _release_lock() -> None:
    try:
        if LOCK_FILE.exists():
            LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def _count_new_sessions(since: datetime) -> int:
    """Count sessions (log files) touched since *since*."""
    try:
        from jarvis_v3.config import LOG_FILE
        log = Path(LOG_FILE)
        if not log.exists():
            return 0
        mtime = datetime.fromtimestamp(log.stat().st_mtime)
        if mtime > since:
            # Rough approximation: one session per 10 lines
            lines = len(log.read_text(encoding="utf-8").splitlines())
            return max(lines // 10, 1)
    except Exception:
        pass

    # Fallback: count files in sessions dir
    try:
        sessions_dir = BASE_DIR / "sessions"
        if not sessions_dir.exists():
            return 0
        return sum(
            1
            for f in sessions_dir.iterdir()
            if f.is_file() and datetime.fromtimestamp(f.stat().st_mtime) > since
        )
    except Exception:
        return 0


def _gather_signals() -> str:
    """Collect recent tasks, errors, and patterns from JARVIS logs."""
    lines: list[str] = []
    try:
        from jarvis_v3.config import LOG_FILE
        log = Path(LOG_FILE)
        if log.exists():
            text = log.read_text(encoding="utf-8", errors="replace")
            recent = text.split("\n")[-200:]
            lines.append("## Recent Tasks\n" + "\n".join(recent))
    except Exception:
        pass

    try:
        from jarvis_v3.config import DEBATE_LOG
        dlog = Path(DEBATE_LOG)
        if dlog.exists():
            text = dlog.read_text(encoding="utf-8", errors="replace")
            recent = text.split("\n")[-20:]
            lines.append("## Recent Debates\n" + "\n".join(recent))
    except Exception:
        pass

    return "\n\n".join(lines) or "(No new signals)"


def _build_prompt(signals: str) -> str:
    return (
        "You are JARVIS's dream-state consolidator. "
        "Read the signals below and produce an updated MEMORY.md entry.\n\n"
        "Rules:\n"
        "1. Keep existing memories that are still relevant.\n"
        "2. Add new facts, patterns, and user preferences discovered recently.\n"
        "3. Remove outdated or redundant items.\n"
        "4. Format as concise bullet points under headings.\n\n"
        f"Signals:\n{signals}\n\n"
        "If there is nothing actionable, reply ONLY: NOOP"
    )


def _run_consolidation() -> str:
    """Fork an agent subagent to compress memories."""
    from jarvis_v3.api_manager import call_with_rotation
    from jarvis_v3.compat.bridge import thread_run

    signals = _gather_signals()
    prompt = _build_prompt(signals)

    async def _call():
        return await call_with_rotation(
            task="dream consolidation",
            task_type="logic",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
        )

    try:
        response = thread_run(_call())
        text = ""
        if hasattr(response, "content"):
            text = response.content[0].text.strip()
        else:
            text = str(response).strip()
        if text.upper().startswith("NOOP"):
            return "[DREAM] Nothing new to consolidate."
        return text
    except Exception as exc:
        _log.error("Dream consolidation LLM call failed: %s", exc, exc_info=True)
        return f"[DREAM ERROR] {exc}"


def _update_memory(new_content: str) -> None:
    """Write consolidated output to ObsidianBrain; fall back to MEMORY_FILE."""
    iso_date = _now().strftime("%Y-%m-%dT%H:%M:%S")
    try:
        from jarvis_v3.obsidian_brain import ObsidianBrain
        brain = ObsidianBrain()
        # Prune: keep only last 3 consolidation notes in memory/ folder
        existing = brain.list_notes(folder="memory")
        consolidation_notes = [n for n in existing if "consolidation" in (n.get("frontmatter", {}).get("tags", []) or [])]
        if len(consolidation_notes) >= 3:
            for note in consolidation_notes[:-3]:
                try:
                    brain.update_note(note["name"], content="", folder="memory", tags=[])
                except Exception:
                    pass
        note_name = f"consolidated_{_now().strftime('%Y-%m-%d')}"
        try:
            brain.create_note(
                note_name,
                new_content,
                folder="memory",
                tags=["consolidation", "auto-dream"],
                metadata={"consolidated_at": iso_date},
            )
        except FileExistsError:
            brain.update_note(
                note_name,
                new_content,
                folder="memory",
                tags=["consolidation", "auto-dream"],
                metadata={"consolidated_at": iso_date},
            )
        _log.info("[DREAM] Wrote consolidation note to ObsidianBrain: memory/%s", note_name)
    except Exception as exc:
        _log.warning("[DREAM] ObsidianBrain unavailable (%s), falling back to MEMORY_FILE", exc)
        _update_memory_fallback(new_content, iso_date)


def _update_memory_fallback(new_content: str, iso_date: str) -> None:
    """Fallback MEMORY_FILE writer when ObsidianBrain is unavailable."""
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    header = f"# JARVIS Memory\n\n*Auto-consolidated at {iso_date}*\n\n"
    try:
        old = MEMORY_FILE.read_text(encoding="utf-8")
        sections = old.split("*Auto-consolidated at")
        if len(sections) > 4:
            old = "*Auto-consolidated at".join(sections[-3:])
    except FileNotFoundError:
        old = ""
    updated = header + new_content + "\n\n---\n\n" + old
    MEMORY_FILE.write_text(updated, encoding="utf-8")


def _now() -> datetime:
    return datetime.now()


def tick() -> str:
    """Check gates and run consolidation if appropriate."""
    state = _read_state()
    last = datetime.fromisoformat(state["last_consolidated_at"])
    now = _now()

    # Gate 1: Time
    if now - last < timedelta(hours=MIN_HOURS):
        return "[DREAM] Time gate not passed."

    # Gate 2: Sessions
    sessions = _count_new_sessions(last)
    if sessions < MIN_SESSIONS:
        return f"[DREAM] Session gate not passed ({sessions}/{MIN_SESSIONS})."

    # Gate 3: Lock
    if not _acquire_lock():
        return "[DREAM] Another process is already consolidating."

    try:
        _log.info("[DREAM] Starting consolidation (%d new sessions)", sessions)
        result = _run_consolidation()
        if not result.startswith("[DREAM"):
            _update_memory(result)
            state["last_consolidated_at"] = now.isoformat()
            _write_state(state)
            _log.info("[DREAM] Consolidation complete. MEMORY.md updated.")
            return "[DREAM] Consolidation complete."
        return result
    finally:
        _release_lock()


def main() -> None:
    """Run the dream daemon loop."""
    _log.info("AutoDream daemon started (tick every %ds)", SCAN_INTERVAL_S)
    try:
        while True:
            summary = tick()
            if "complete" in summary or "ERROR" in summary:
                _log.info(summary)
            time.sleep(SCAN_INTERVAL_S)
    except KeyboardInterrupt:
        _log.info("AutoDream daemon stopped.")


__all__ = ["tick", "main"]
