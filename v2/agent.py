"""JARVIS Master Agent v2.0

Core execution loop with:
  • Experience-based model routing
  • Confidence scoring
  • Automatic debate on decision questions
  • Self-evolution on tool failures
  • Reasoning trace logging
  • Episodic memory recall at task start
  • Model swap on failures (up to 3)
"""
from __future__ import annotations

import base64
import json
import logging
import os
import sys
import time
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final, Literal

import anthropic

from config import (
    BLOCKED_COMMANDS,
    DEBATE_TRIGGER_WORDS,
    FCC_AUTH_TOKEN,
    FCC_BASE_URL,
    FALLBACK_MODEL,
    LOG_FILE,
    MAX_TOKENS,
)

# Lazy import of heavy deps to keep startup fast and avoid circular imports
if sys.version_info >= (3, 10):
    from typing import TypeAlias
else:
    from typing_extensions import TypeAlias

_log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
#  Types
# ═══════════════════════════════════════════════════════════
ToolUse: TypeAlias = dict[str, Any]
StatusCallback: TypeAlias = Callable[[str], Any] | None
TokenCallback: TypeAlias = Callable[[str], Any] | None

# ═══════════════════════════════════════════════════════════
#  Anthropic client (singleton)
# ═══════════════════════════════════════════════════════════
_client: anthropic.Anthropic | None = None


def _anthropic_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(
            base_url=FCC_BASE_URL, api_key=FCC_AUTH_TOKEN or "freecc"
        )
    return _client


# ═══════════════════════════════════════════════════════════
#  System prompt
# ═══════════════════════════════════════════════════════════
_SYSTEM_PROMPT_TEMPLATE: Final = """You are JARVIS — a hyper-capable AI operating system assistant running on CachyOS Linux with Hyprland.

## User Context (Who you work for)
{life_state}

## Your Identity
You are not a chatbot. You are an autonomous agent that ACTS. You have direct access to the OS, browser, files, and internet. You think fast and execute precisely.

## Available Tool Categories
- **OS Control**: `os_hardware_control` (volume, brightness, wifi, bt, lock, suspend), `os_window_control` (workspaces, focus), `os_process_control` (launch, kill).
- **Media**: `media_control` (play/pause/next), `lightning_play` (instant music/video).
- **Files & Packages**: `git_ops`, `package_ops` (paru search/install), `find_and_open_file`, `write_file`, `read_file`.
- **System & Research**: `system_health_report`, `gemini_search` (web), `os_mind_meld` (deep state), `semantic_scan` (window map).
- **Intelligence**: `delegate_swarm` (spawn specialists), `store_successful_task` (learn), `retrieve_past_task` (recall).

## Core Protocols (execute in order)
1. **RECALL**: Use `retrieve_past_task` first — check if you've solved something similar before.
2. **SENSE**: Use `os_mind_meld` + `semantic_scan` in parallel for any desktop task.
3. **ACT**: For simple OS commands (workspace, volume, bluetooth, file moves), use `high_speed_plan` or `bash` directly. Do NOT delegate simple tasks.
4. **DELEGATE**: For multi-domain complex tasks (e.g., "research X and write code for Y"), use `delegate_swarm` to spawn specialists.
5. **TEST-COMMIT**: Use `sandboxed_bash` to verify code, then `deploy_to_system` to install.
6. **LEARN**: On success, call `store_successful_task` to save the action sequence.
7. **SPEAK**: Use `speak` to announce completions.

## Rules
- Never explain what you're ABOUT to do. Just do it.
- Batch all GUI interactions into a single `human_batch` call.
- If a tool fails twice with the same error, use `gemini_search` to find the fix.
- Keep responses under 3 paragraphs unless asked for detail.
- BLOCKED: rm -rf /, dd if=, mkfs, or any mass destruction command.
"""


# ═══════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════
def get_life_state() -> str:
    """Load persistent identity context."""
    try:
        from life_state_manager import get_identity_context
        return get_identity_context()
    except Exception:
        _log.debug("life_state_manager unavailable, using default identity")
        return "User: Dhairya"


def get_os_context() -> str:
    """Get current active window for context injection."""
    try:
        import subprocess
        aw = json.loads(
            subprocess.run(
                ["hyprctl", "activewindow", "-j"],
                capture_output=True, text=True, timeout=2,
            ).stdout
        )
        return f"\n[ACTIVE WINDOW: {aw.get('class', '?')} — {aw.get('title', '?')}]\n"
    except Exception:
        _log.debug("Could not get OS context (hyprctl failed)")
        return ""


def _log_task(
    task: str,
    result: str,
    tools_used: list[str],
    model: str,
    duration: float,
    success: bool,
    *,
    task_type: str = "unknown",
    iterations: int = 0,
    swap_count: int = 0,
) -> None:
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "task": task,
        "task_type": task_type,
        "result_preview": result[:500],
        "tools_used": tools_used,
        "model": model,
        "duration_s": round(duration, 1),
        "success": success,
        "iterations": iterations,
        "swap_count": swap_count,
        "user_rating": None,
    }
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        _log.warning("Could not append to log file: %s", exc)


def rate_last_task(rating: Literal["good", "bad"]) -> str:
    """Update the 'user_rating' of the most recent log entry."""
    if rating not in ("good", "bad"):
        return "Rating must be 'good' or 'bad'."

    try:
        if not LOG_FILE.exists():
            return "No tasks to rate."
        lines = LOG_FILE.read_text(encoding="utf-8").splitlines(keepends=True)
        if not lines:
            return "No tasks to rate."

        last_record = json.loads(lines[-1])
        last_record["user_rating"] = rating
        lines[-1] = json.dumps(last_record, ensure_ascii=False) + "\n"
        LOG_FILE.write_text("".join(lines), encoding="utf-8")
        return f"Thank you! Marked last task as '{rating}'."
    except json.JSONDecodeError:
        return "Corrupt log file — could not rate."
    except Exception as exc:
        return f"Error rating task: {exc}"


# ═══════════════════════════════════════════════════════════
#  Main agent loop
# ═══════════════════════════════════════════════════════════
def run_agent(
    task: str,
    status_callback: StatusCallback = None,
    token_callback: TokenCallback = None,
    session_id: str = "default",
) -> str:
    """Main agent loop. Returns final response string.

    Args:
        task: The user instruction.
        status_callback: Optional live-status function (Telegram/CLI).
        token_callback: Optional token streaming function.
        session_id: Session key for multi-turn context.

    Returns:
        The agent's final response.
    """
    from fast_path_router import execute_fast_path
    from session_memory import add_session_turn, get_session_context

    start = time.time()

    # ── Fast-path local router ────────────────────────────
    local_result = execute_fast_path(task)
    if local_result:
        duration = time.time() - start
        _log_task(task, local_result, ["fast_path"], "local-router", duration, True)
        add_session_turn(session_id, "user", task)
        add_session_turn(session_id, "assistant", local_result)
        if token_callback:
            token_callback(local_result)
        return local_result

    # ── Classify and route ───────────────────────────────
    from orchestrator import classify_task

    task_type = classify_task(task)
    tools_used: list[str] = []

    def _status(msg: str) -> None:
        if status_callback:
            status_callback(msg)
        _log.info("%s", msg)

    _status(f"🧠 Swarm Orchestrator [{task_type}]")

    # ── Debate for decision questions ─────────────────────
    if any(w in task.lower() for w in DEBATE_TRIGGER_WORDS):
        _status("⚖️ Debate mode activated...")
        try:
            from debate import run_debate
            result = run_debate(task)
            duration = time.time() - start
            _log_task(
                task, result, ["debate"], "debate-swarm", duration, True,
                task_type=task_type, iterations=1,
            )
            from orchestrator import record_outcome
            record_outcome(task_type, "debate-swarm", True)
            add_session_turn(session_id, "user", task)
            add_session_turn(session_id, "assistant", result)
            return result
        except Exception as exc:
            _log.warning("Debate failed (%s), falling back to single model", exc)
            _status(f"⚠️ Debate failed ({exc}), falling back to single model")

    # ── Recall similar past tasks ─────────────────────────
    from episodic_memory import retrieve_past_task
    past = retrieve_past_task(task)

    # ── Dynamic prompt (A/B testing) ──────────────────────
    try:
        from prompt_variants import get_random_variant, log_experiment
        variant_id, variant_text = get_random_variant()
        log_experiment(task, variant_id)
        identity_prompt = (
            f"{variant_text}\n\n## User Context (Who you work for)\n"
            f"{get_life_state()}"
        )
    except Exception:
        _log.debug("Prompt variant unavailable, using default system prompt")
        identity_prompt = _SYSTEM_PROMPT_TEMPLATE.format(life_state=get_life_state())

    system_ctx = identity_prompt + get_os_context()
    if past and "No similar" not in past:
        system_ctx += f"\n\n[MEMORY] {past}"
        _status("💾 Past episode recalled")

    # ── Load session history ──────────────────────────────
    history = get_session_context(session_id)
    messages: list[dict[str, Any]] = []
    for turn in history:
        messages.append({
            "role": turn["role"],
            "content": [{"type": "text", "text": turn["content"]}],
        })
    messages.append({"role": "user", "content": [{"type": "text", "text": task}]})

    # ── Main agentic loop ─────────────────────────────────
    iteration = 0
    max_iter = 20
    final = ""
    response: Any = None  # Holds the last LLM response for bookkeeping

    while iteration < max_iter:
        iteration += 1
        try:
            from api_manager import call_with_rotation
            from tools import TOOL_DEFINITIONS, dispatch_tool

            response = call_with_rotation(
                task=task,
                task_type=task_type,
                messages=messages,
                system=system_ctx,
                tools=TOOL_DEFINITIONS,
                stream=True,
                token_callback=token_callback,
            )
        except Exception as exc:
            _log.error("LLM call failed: %s", exc, exc_info=True)
            final = f"**Error**: {exc}"
            break

        # Handle unexpected string/bare return types (cached result etc.)
        if not hasattr(response, "content"):
            final = str(response)
            break

        messages.append({"role": "assistant", "content": response.content})
        tool_uses = [b for b in response.content if getattr(b, "type", None) == "tool_use"]

        if not tool_uses:
            texts = [b for b in response.content if getattr(b, "type", None) == "text"]
            final = texts[0].text.strip() if texts else "Task complete."

            # ── Confidence check ──────────────────────────
            try:
                from confidence import score as conf_score
                conf = conf_score(task, final)
                if conf < 0.35:
                    _status(f"🔍 Low confidence ({conf:.0%}), searching for more info...")
                    from tools import execute_gemini_search
                    extra = execute_gemini_search(f"authoritative answer: {task[:200]}")
                    final = f"{final}\n\n---\n*Supplementary research:*\n{extra[:800]}"
            except Exception:
                _log.debug("Confidence check skipped (unavailable or failed)")

            break

        # ── Execute tools ─────────────────────────────────
        tool_results: list[dict[str, Any]] = []
        for tool in tool_uses:
            _status(f"🔧 `{tool.name}`")
            tools_used.append(tool.name)

            try:
                output = dispatch_tool(tool.name, tool.input)
            except Exception as exc:
                _log.error("Tool %s raised %s", tool.name, exc, exc_info=True)
                output = f"[ERROR] {exc}"

            # Screenshot → base64 image for model
            if tool.name == "take_screenshot" and not str(output).startswith("[ERROR]"):
                try:
                    img_path = Path(str(output))
                    if img_path.exists():
                        img_b64 = base64.b64encode(img_path.read_bytes()).decode()
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": getattr(tool, "id", ""),
                            "content": [{
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": img_b64,
                                },
                            }],
                        })
                        continue
                except Exception:
                    _log.debug("Screenshot base64 encoding failed", exc_info=True)

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": getattr(tool, "id", ""),
                "content": str(output)[:8000],
            })

            # ── Self-heal on repeated tool errors ─────────
            if str(output).startswith("[ERROR]") and iteration > 2:
                try:
                    from self_evolution import attempt_self_evolution
                    evo_result = attempt_self_evolution(task, str(output))
                    _status(f"🧬 {evo_result}")
                except Exception:
                    _log.debug("Self-evolution failed", exc_info=True)

        if tool_results:
            messages.append({"role": "user", "content": tool_results})
        else:
            # Safety valve: no results means something went wrong
            break

    # ── Post-task bookkeeping ─────────────────────────────
    duration = time.time() - start
    success = not final.startswith("**Error")

    actual_model = "unknown"
    if response is not None and hasattr(response, "model"):
        actual_model = response.model  # type: ignore[attr-defined]

    from orchestrator import record_outcome
    record_outcome(task_type, actual_model, success)
    _log_task(
        task, final, list(set(tools_used)), actual_model, duration, success,
        task_type=task_type, iterations=iteration, swap_count=0,
    )

    if success and tools_used:
        from episodic_memory import store_successful_task
        store_successful_task(task, list(set(tools_used)))

    # ── Grow knowledge graph ──────────────────────────────
    if success and final and "Error" not in final:
        try:
            from knowledge_extractor import extract_and_add_to_graph
            extract_and_add_to_graph(task, final)
        except Exception:
            _log.debug("Knowledge extraction skipped", exc_info=True)

    add_session_turn(session_id, "user", task)
    add_session_turn(session_id, "assistant", final)

    _status(f"✅ Done in {duration:.1f}s")
    return final if final else "[AGENT] Hit max iterations without response."


__all__ = ["run_agent", "rate_last_task", "get_life_state", "get_os_context"]
