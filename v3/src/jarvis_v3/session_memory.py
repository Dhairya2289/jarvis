from __future__ import annotations

import json
import logging
from collections import deque
from pathlib import Path
from typing import Deque, Dict, List, Optional

LOG = logging.getLogger(__name__)

BASE_DIR = Path.home() / ".jarvis"
SESSION_FILE = BASE_DIR / "sessions.json"
MAX_HISTORY = 20

# Memory structure: { session_id: deque([ {"role": "user", "content": "..."}, ... ]) }
_sessions: Dict[str, Deque[Dict[str, str]]] = {}


def _load_sessions() -> None:
    """Load sessions from disk."""
    global _sessions
    if not SESSION_FILE.exists():
        LOG.debug("Session file does not exist: %s", SESSION_FILE)
        return
    try:
        data = json.loads(SESSION_FILE.read_text())
        for sid, history in data.items():
            _sessions[sid] = deque(history, maxlen=MAX_HISTORY)
        LOG.debug("Loaded sessions from %s", SESSION_FILE)
    except Exception as e:
        LOG.warning("Failed to load sessions: %s", e)


def _save_sessions() -> None:
    """Persist sessions to disk."""
    try:
        data = {sid: list(hist) for sid, hist in _sessions.items()}
        SESSION_FILE.write_text(json.dumps(data, indent=2))
        LOG.debug("Saved sessions to %s", SESSION_FILE)
    except Exception as e:
        LOG.error("Failed to save sessions: %s", e)


def get_session_context(session_id: str) -> List[Dict[str, str]]:
    """Get the message history for a specific session.

    Args:
        session_id: Unique identifier for the session.

    Returns:
        List of message dictionaries with 'role' and 'content'.
    """
    if session_id not in _sessions:
        LOG.debug("Session ID not found: %s", session_id)
        return []
    context = list(_sessions[session_id])
    LOG.debug("Retrieved context for session %s (%d turns)", session_id, len(context))
    return context


def add_session_turn(session_id: str, role: str, content: str) -> None:
    """Add a new turn to the session history.

    Args:
        session_id: Unique identifier for the session.
        role: Role of the speaker (e.g., 'user', 'assistant').
        content: Message content.
    """
    if session_id not in _sessions:
        _sessions[session_id] = deque(maxlen=MAX_HISTORY)
        LOG.debug("Created new session deque for %s", session_id)
    
    _sessions[session_id].append({"role": role, "content": content})
    LOG.debug("Added turn to session %s: %s", session_id, content[:50])
    _save_sessions()
    # Mirror to Obsidian (non-breaking)
    _mirror_to_obsidian(session_id, list(_sessions[session_id]))


def _mirror_to_obsidian(session_id: str, messages: list[dict[str, str]]) -> None:
    """Mirror session to Obsidian Brain (optional, non-breaking)."""
    try:
        from jarvis_v3.obsidian_brain import ObsidianBrain
        content_lines = [f"## Session {session_id}"]
        for msg in messages:
            role = msg.get("role", "?")
            content_lines.append(f"\n**{role}**: {msg.get('content', '')}")
        content = "\n".join(content_lines)
        ObsidianBrain().create_note(
            name=f"session_{session_id}",
            content=content,
            folder="sessions",
            tags=["session"],
        )
    except Exception:
        pass  # non-breaking mirror


def clear_session(session_id: str) -> None:
    """Clear history for a session.

    Args:
        session_id: Unique identifier for the session to clear.
    """
    if session_id in _sessions:
        _sessions[session_id].clear()
        _save_sessions()
        LOG.info("Cleared session: %s", session_id)
    else:
        LOG.debug("Attempted to clear non-existent session: %s", session_id)


# Initial load
_load_sessions()

# Define public API
__all__: List[str] = [
    "get_session_context",
    "add_session_turn",
    "clear_session",
]