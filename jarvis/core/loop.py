"""
JARVIS Unified Agent Loop — core/loop.py
────────────────────────────────────────
Single async entry point: input → intent → dispatch → response → memory.

Handles voice/telegram/cli uniformly by accepting a string and source tag.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from jarvis.api_manager import ApiManager, MockResponse
from jarvis.context_engine import Intent, classify_intent
from jarvis.obsidian_brain import ObsidianBrain
from jarvis.tools import dispatch_tool

_LOG = logging.getLogger(__name__)


# ── Tool keyword map ──────────────────────────────────────
# Maps query keywords to the best-matching tool name.
_TOOL_TRIGGERS: dict[str, tuple[str, ...]] = {
    "system_health_report": (
        "check my system", "system health", "cpu", "memory", "disk",
        "how's my computer", "system status", "machine status",
    ),
    "take_screenshot": (
        "screenshot", "capture screen", "take a picture", "what do you see",
    ),
    "bash": (
        "run ", "execute ", "terminal", "bash", "command line",
    ),
    "compress_context": (
        "compress", "summarise session", "summarize session",
    ),
}


def _best_matching_tool(user_input: str) -> str | None:
    """Return the tool name that best matches the user input, or None."""
    lower = user_input.lower()
    best_tool: str | None = None
    best_hits = 0

    for tool_name, triggers in _TOOL_TRIGGERS.items():
        hits = sum(1 for t in triggers if t in lower)
        if hits > best_hits:
            best_hits = hits
            best_tool = tool_name

    # Always allow system_health_report for "check my system"
    if best_tool is None:
        if any(k in lower for k in ("system", "health", "cpu", "ram", "disk")):
            return "system_health_report"

    return best_tool


# ── Default response when no specialist handles the input ─
async def _default_chat(
    user_input: str, api: ApiManager
) -> str:
    """Echo back a friendly no-specialist response via the LLM."""
    try:
        messages = [{"role": "user", "content": user_input}]
        resp: MockResponse = await api.call(
            task=user_input,
            task_type="chat",
            messages=messages,
            system="You are JARVIS, a helpful AI assistant. Keep responses short and direct.",
            max_tokens=512,
        )
        texts = [c.text for c in resp.content if getattr(c, "type", None) == "text"]
        return texts[0].strip() if texts else "I'm not sure how to help with that."
    except Exception as exc:
        _LOG.warning("Default chat fallback failed: %s", exc)
        return f"I encountered an error: {exc}"


# ── Main Loop ─────────────────────────────────────────────

class JARVISLoop:
    """
    Unified async agent loop.

    Usage::

        loop = JARVISLoop()
        response = await loop.run_once("check my system", source="cli")
        print(response)
    """

    def __init__(
        self,
        vault_path: str | None = None,
        session_id: str = "default",
    ):
        self.api = ApiManager()
        self.brain = ObsidianBrain(vault_path=str(vault_path) if vault_path else None)
        self.session_id = session_id
        self._turn_count = 0

    # ── Lifecycle ────────────────────────────────────────

    async def __aenter__(self):
        await self.api.__aenter__()
        return self

    async def __aexit__(self, *args):
        await self.api.__aexit__(*args)

    # ── Core ─────────────────────────────────────────────

    async def run_once(
        self,
        user_input: str,
        source: str = "cli",
    ) -> str:
        """
        Execute one full pass: classify → dispatch → log → return.

        Parameters
        ----------
        user_input: raw query string from the user.
        source: one of "cli", "telegram", "voice", "api" — stored in the
                Obsidian session note for auditability.

        Returns
        -------
        str — the response to surface to the user.
        """
        if not user_input or not user_input.strip():
            return "I didn't receive any input."

        self._turn_count += 1
        start = time.time()

        # ── 1. Intent Classification ────────────────────
        intent: Intent = classify_intent(user_input)
        _LOG.debug(
            "Intent → specialist=%s category=%s confidence=%.2f",
            intent.specialist, intent.category, intent.confidence,
        )

        # ── 2. Route & Dispatch ─────────────────────────
        if intent.specialist == "tools":
            tool_name = _best_matching_tool(user_input)
            if tool_name:
                result = dispatch_tool(tool_name, {})
            else:
                # Fallback: run general tool classifier on the query
                result = dispatch_tool("system_health_report", {})

        elif intent.specialist == "agent":
            # Agent specialist → LLM call via ApiManager
            messages = [{"role": "user", "content": user_input}]
            resp: MockResponse = await self.api.call(
                task=user_input,
                task_type=intent.category,
                messages=messages,
                system="You are JARVIS. Keep responses concise and helpful.",
                max_tokens=1024,
            )
            texts = [c.text for c in resp.content if getattr(c, "type", None) == "text"]
            result = texts[0].strip() if texts else "Done."

        elif intent.specialist == "episodic_memory":
            from jarvis.episodic_memory import retrieve_past_task
            result = retrieve_past_task(user_input)

        else:
            # Unknown specialist — try default chat
            result = await _default_chat(user_input, self.api)

        duration_s = time.time() - start

        # ── 3. Log Interaction to Obsidian ──────────────
        await self._log_interaction(
            user_input=user_input,
            intent=intent,
            result=result,
            source=source,
            duration_s=duration_s,
        )

        # ── 4. Auto-Review / Memory ─────────────────────
        await self._auto_memory(user_input, result, intent)

        return str(result)

    # ── Logging ──────────────────────────────────────────

    async def _log_interaction(
        self,
        user_input: str,
        intent: Intent,
        result: str,
        source: str,
        duration_s: float,
    ) -> None:
        """Append the interaction to the current session note in Obsidian."""
        try:
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            excerpt = str(result)[:120].replace("\n", " ")
            entry = (
                f"## [{ts}] [{source.upper()}] {intent.category} → {intent.specialist}\n"
                f"**Q:** {user_input}\n"
                f"**A:** {excerpt}...\n"
                f"_(took {duration_s:.1f}s, confidence={intent.confidence:.2f})_\n"
            )
            self.brain.append_daily(entry.strip())

            # Also create a dedicated session note for richer history
            session_name = f"session_{self.session_id}"
            session_folder = "sessions"
            session_content = (
                f"# Session: {self.session_id}\n"
                f"**Started:** {ts}\n"
                f"**Source:** {source}\n\n"
                f"## Interactions\n{entry}"
            )
            try:
                self.brain.create_note(
                    name=session_name,
                    content=session_content,
                    folder=session_folder,
                    tags=["session", source],
                    metadata={
                        "turn_count": self._turn_count,
                        "last_ts": ts,
                    },
                )
            except FileExistsError:
                # Append to existing session note
                existing = self.brain.read_note(session_name, folder=session_folder)
                updated = existing["content"] + "\n" + entry
                self.brain.update_note(
                    session_name,
                    content=updated,
                    folder=session_folder,
                    metadata={"last_ts": ts, "turn_count": self._turn_count},
                )
        except Exception as exc:
            _LOG.warning("Obsidian logging failed: %s", exc)

    async def _auto_memory(
        self, user_input: str, result: str, intent: Intent
    ) -> None:
        """Store notable interactions in episodic memory."""
        try:
            from jarvis.episodic_memory import store_successful_task
            from jarvis.memdir import MemDir

            # If a tool was used, record it in episodic memory
            if intent.specialist == "tools":
                tool_name = _best_matching_tool(user_input)
                if tool_name:
                    store_successful_task(user_input, [tool_name])

            # Store facts / preferences in memdir if confidence is high
            if intent.confidence > 0.7 and intent.category in ("logic", "system"):
                MemDir().add(
                    content=f"User asked about '{user_input[:60]}' → {str(result)[:80]}",
                    mem_type="task",
                    confidence=intent.confidence,
                    tags=[intent.category, intent.specialist],
                )
        except Exception as exc:
            _LOG.debug("Auto-memory skipped: %s", exc)

    # ── Convenience run wrapper ──────────────────────────

    async def run(self, user_input: str, source: str = "cli") -> str:
        """Alias for run_once — provided for semantic clarity."""
        return await self.run_once(user_input, source=source)