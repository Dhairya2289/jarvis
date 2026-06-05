"""
JARVIS V3 — Master Agent
──────────────────────────────────────────────────────────────
Async agent loop with:
  • Experience-based model routing
  • Confidence scoring
  • Automatic debate on decision questions
  • Self-evolution on tool failures
  • Reasoning trace logging
  • Episodic memory recall
  • Async streaming via ApiManager
"""

import asyncio
import json
import base64
import time
from datetime import datetime
from typing import Any, Callable, List, Optional

from jarvis_v3.config import MAX_TOKENS, LOG_FILE, FALLBACK_MODEL, DEBATE_TRIGGER_WORDS
from jarvis_v3.api_manager import call_with_rotation, MockContent


SYSTEM_PROMPT = """You are JARVIS — a hyper-capable AI operating system assistant running on CachyOS Linux with Hyprland.

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


def get_life_state() -> str:
    """Load persistent identity context."""
    try:
        # Defer import to avoid circular deps
        from jarvis_v3.life_state_manager import get_identity_context
        return get_identity_context()
    except Exception:
        return "User: Dhairya"


def get_os_context() -> str:
    """Get current active window for context injection."""
    try:
        import subprocess, json as _json
        aw = _json.loads(
            subprocess.run(
                ["hyprctl", "activewindow", "-j"],
                capture_output=True, text=True, timeout=3
            ).stdout
        )
        return f"\n[ACTIVE WINDOW: {aw.get('class','?')} — {aw.get('title','?')}]\n"
    except Exception:
        return ""


def _log_task(
    task: str,
    result: str,
    tools_used: List[str],
    model: str,
    duration: float,
    success: bool,
    task_type: str = "unknown",
    iterations: int = 0,
    swap_count: int = 0,
):
    record = {
        "ts": datetime.utcnow().isoformat(),
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
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass


def rate_last_task(rating: str) -> str:
    if rating not in ["good", "bad"]:
        return "Rating must be 'good' or 'bad'."
    try:
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()
        if not lines:
            return "No tasks to rate."
        last_record = json.loads(lines[-1])
        last_record["user_rating"] = rating
        lines[-1] = json.dumps(last_record) + "\n"
        with open(LOG_FILE, "w") as f:
            f.writelines(lines)
        return f"Thank you! Marked last task as '{rating}'."
    except Exception as e:
        return f"Error rating task: {e}"


async def run_agent(
    task: str,
    status_callback: Optional[Callable[[str], None]] = None,
    token_callback: Optional[Callable[[str], None]] = None,
    session_id: str = "default",
) -> str:
    """
    Main agent loop. Returns final response string.
    """
    from jarvis_v3.orchestrator import classify_task, record_outcome
    from jarvis_v3.fast_path_router import execute_fast_path

    start = time.time()

    # ── Fast-Path Local Router ────────────────────────────
    local_result = execute_fast_path(task)
    if local_result:
        duration = time.time() - start
        _log_task(task, local_result, ["fast_path"], "local-router", duration, True)
        return local_result

    task_type = classify_task(task)
    tools_used: List[str] = []

    def _status(msg: str):
        if status_callback:
            status_callback(msg)
        else:
            print(f"  {msg}")

    _status(f"🧠 Swarm Orchestrator [{task_type}]")

    # ── Auto-debate for decision questions ────────────────
    if any(w in task.lower() for w in DEBATE_TRIGGER_WORDS):
        _status("⚖️ Debate mode activated...")
        try:
            from jarvis_v3.debate import run_debate
            result = await run_debate(task)
            duration = time.time() - start
            _log_task(
                task, result, ["debate"], "debate-swarm", duration, True,
                task_type=task_type, iterations=1,
            )
            record_outcome(task_type, "debate-swarm", True)
            return result
        except Exception as e:
            _status(f"⚠️ Debate failed ({e}), falling back to single model")

    # ── Recall similar past tasks ─────────────────────────
    try:
        from jarvis_v3.episodic_memory import retrieve_past_task
        past = retrieve_past_task(task)
    except Exception:
        past = None

    # ── Dynamic Prompt (A/B Testing) ─────────────────────
    try:
        from jarvis_v3.prompt_variants import get_random_variant, log_experiment
        variant_id, variant_text = get_random_variant()
        log_experiment(task, variant_id)
        identity_prompt = f"{variant_text}\n\n## User Context (Who you work for)\n{get_life_state()}"
    except Exception:
        identity_prompt = SYSTEM_PROMPT.format(life_state=get_life_state())

    system_ctx = identity_prompt + get_os_context()
    if past and "No similar" not in past:
        system_ctx += f"\n\n[MEMORY] {past}"
        _status("💾 Past episode recalled")

    # ── Session history ──────────────────────────────────
    try:
        from jarvis_v3.session_memory import get_session_context, add_session_turn
        history = get_session_context(session_id)
    except Exception:
        history = []
        add_session_turn = None  # type: ignore

    messages: List[dict] = []
    for turn in history:
        messages.append({"role": turn["role"], "content": [{"type": "text", "text": turn["content"]}]})
    messages.append({"role": "user", "content": [{"type": "text", "text": task}]})

    iteration = 0
    max_iter = 20
    final = ""

    while iteration < max_iter:
        iteration += 1
        try:
            response = await call_with_rotation(
                task=task,
                task_type=task_type,
                messages=messages,
                system=system_ctx,
                tools=None,  # tools loaded below
                stream=True,
                token_callback=token_callback,
            )
        except Exception as e:
            final = f"**Error**: {e}"
            break

        messages.append({"role": "assistant", "content": response.content})
        tool_uses = [b for b in response.content if getattr(b, "type", None) == "tool_use"]

        # ── No tools = final answer ───────────────────────
        if not tool_uses:
            texts = [b for b in response.content if getattr(b, "type", None) == "text"]
            final = texts[0].text.strip() if texts else "Task complete."

            # ── Confidence check ──────────────────────────
            try:
                from jarvis_v3.confidence import score as conf_score
                conf = conf_score(task, final)
                if conf < 0.35:
                    _status(f"🔍 Low confidence ({conf:.0%}), searching...")
                    # TODO: integrate gemini search
            except Exception:
                pass
            break

        # ── Execute tools ─────────────────────────────────
        tool_results: List[dict] = []
        for tool in tool_uses:
            _status(f"🔧 `{tool.name}`")
            tools_used.append(tool.name)

            try:
                from jarvis_v3.tools import dispatch_tool
                output = dispatch_tool(tool.name, getattr(tool, "input", {}))
            except Exception as e:
                output = f"[ERROR] {e}"

            # Screenshot → send as image to model
            if tool.name == "take_screenshot" and not str(output).startswith("[ERROR]"):
                try:
                    with open(output, "rb") as f:
                        img_b64 = base64.b64encode(f.read()).decode()
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
                    pass

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": getattr(tool, "id", ""),
                "content": str(output)[:8000],
            })

            # ── Self-heal on tool errors ──────────────────
            if str(output).startswith("[ERROR]") and iteration > 2:
                try:
                    from jarvis_v3.self_evolution import attempt_self_evolution
                    evo_result = attempt_self_evolution(task, str(output))
                    _status(f"🧬 {evo_result}")
                except Exception:
                    pass

        if tool_results:
            messages.append({"role": "user", "content": tool_results})
        else:
            if not tool_uses:
                break
            iteration = max_iter

    # ── Post-task bookkeeping ──────────────────────────────
    duration = time.time() - start
    success = not final.startswith("**Error")
    actual_model = getattr(response, "model", "unknown") if "response" in dir() else "unknown"

    record_outcome(task_type, actual_model, success)
    _log_task(
        task, final, list(set(tools_used)), actual_model, duration, success,
        task_type=task_type, iterations=iteration, swap_count=0,
    )

    if success and tools_used:
        try:
            from jarvis_v3.episodic_memory import store_successful_task
            store_successful_task(task, list(set(tools_used)))
        except Exception:
            pass

    # ── Grow Knowledge Graph ──────────────────────────────
    if success and final and "Error" not in final:
        try:
            from jarvis_v3.knowledge_extractor import extract_and_add_to_graph
            extract_and_add_to_graph(task, final)
        except Exception:
            pass

    # ── Grow session memory ───────────────────────────────
    if add_session_turn and final:
        add_session_turn(session_id, "user", task)
        add_session_turn(session_id, "assistant", final)

    _status(f"✅ Done in {duration:.1f}s")
    return final if final else "[AGENT] Hit max iterations without response."
