from __future__ import annotations

import importlib.util
import json
import logging
import os
import sys
import textwrap
import traceback
from pathlib import Path
from typing import Any, Dict, Tuple, Optional

import anthropic
from jarvis_v3.config import FCC_BASE_URL, FCC_AUTH_TOKEN, BRAIN_MODEL, BASE_DIR, SANDBOX_DIR

_LOG = logging.getLogger(__name__)

client = anthropic.Anthropic(base_url=FCC_BASE_URL, api_key=FCC_AUTH_TOKEN)
TOOLS_FILE = Path(__file__).parent / "tools.py"
EVOLVED_DIR = BASE_DIR / "evolved_tools"
EVOLVED_DIR.mkdir(exist_ok=True)

# ── Gap Analysis ──────────────────────────────────────────

def analyze_capability_gap(task: str, error: str) -> Dict[str, Any]:
    """
    Ask the Brain: what tool is missing? What should it do?
    Returns {name, description, python_code} or {'name': None} if no tool missing.

    Args:
        task: The task that failed.
        error: The error message from the failure.

    Returns:
        Dictionary with keys: name (str or None), description (str), why_missing (str).
    """
    prompt = (
        f"A Jarvis AI agent failed to complete this task:\n"
        f"Task: {task}\nError: {error}\n\n"
        f"Analyze what Python tool function is MISSING that would fix this.\n"
        f"Respond ONLY in this exact JSON format (no markdown):\n"
        f'{{"name": "tool_name", "description": "What it does", '
        f'"why_missing": "Gap explanation"}}\n\n'
        f"If no tool is missing (just a logic error), return: {{\"name\": null}}"
    )
    try:
        r = client.messages.create(
            model=BRAIN_MODEL, max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = r.content[0].text.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        _LOG.warning("Failed to analyze capability gap: %s", e)
        return {"name": None}

def design_tool(name: str, description: str, task_context: str) -> str:
    """
    Write the actual Python function + tool schema for the new capability.
    Returns the Python source code.

    Args:
        name: The name of the tool.
        description: Description of what the tool does.
        task_context: The context of the task that requires this tool.

    Returns:
        Python source code string for the tool.
    """
    prompt = (
        f"Write a Python tool function for a Jarvis AI system.\n\n"
        f"Tool name: {name}\n"
        f"Description: {description}\n"
        f"Task context that requires it: {task_context}\n\n"
        f"Requirements:\n"
        f"- Function named execute_{name}()\n"
        f"- Must return a string result\n"
        f"- Include all necessary imports inside the function\n"
        f"- Handle exceptions, return '[ERROR] ...' on failure\n"
        f"- After the function, add a TOOL_SCHEMA dict with name/description/input_schema\n"
        f"- Keep it under 60 lines total\n\n"
        f"Output ONLY valid Python code, no explanations, no markdown fences."
    )
    try:
        r = client.messages.create(
            model=BRAIN_MODEL, max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        code = r.content[0].text.strip()
        # Strip any accidental markdown fences
        if "```" in code:
            code = code.split("```")[1]
            if code.startswith("python\n"):
                code = code[7:]
        return code
    except Exception as e:
        _LOG.error("Error generating tool: %s", e)
        return f"# Error generating tool: {e}"

# ── Sandbox Test ──────────────────────────────────────────

def test_tool_in_sandbox(tool_code: str, tool_name: str) -> Tuple[bool, str]:
    """
    Write tool to sandbox file, try importing it, run basic exec.
    Returns (success, output)

    Args:
        tool_code: The Python source code for the tool.
        tool_name: The name of the tool.

    Returns:
        Tuple of (success boolean, output message).
    """
    test_file = EVOLVED_DIR / f"test_{tool_name}.py"
    test_file.write_text(tool_code)

    try:
        spec = importlib.util.spec_from_file_location(f"test_{tool_name}", test_file)
        if spec is None:
            return False, f"[TEST FAILED] Could not load module spec for {tool_name}"
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Verify function exists
        fn_name = f"execute_{tool_name}"
        if not hasattr(module, fn_name):
            return False, f"Function {fn_name} not found in generated code."

        # Verify schema exists
        if not hasattr(module, "TOOL_SCHEMA"):
            return False, "TOOL_SCHEMA not defined."

        return True, f"[TEST PASSED] {fn_name} loaded and schema valid."
    except Exception as e:
        _LOG.error("Sandbox test failed for %s: %s", tool_name, e)
        return False, f"[TEST FAILED] {traceback.format_exc(limit=3)}"
    finally:
        test_file.unlink(missing_ok=True)

# ── Hot-Reload ────────────────────────────────────────────

def hot_reload_tool(tool_code: str, tool_name: str) -> str:
    """
    Save evolved tool, dynamically add its executor + schema to the live tools module.
    Also appends to evolved_tools/ for persistence across restarts.

    Args:
        tool_code: The Python source code for the tool.
        tool_name: The name of the tool.

    Returns:
        Status message.
    """
    # Persist the tool
    evolved_file = EVOLVED_DIR / f"{tool_name}.py"
    evolved_file.write_text(tool_code)

    # Load it
    spec = importlib.util.spec_from_file_location(tool_name, evolved_file)
    if spec is None:
        return f"[ERROR] Could not load module spec for {tool_name}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    fn_name = f"execute_{tool_name}"
    fn = getattr(module, fn_name)
    schema = getattr(module, "TOOL_SCHEMA")

    # Inject into live tools module
    import tools as tools_module
    setattr(tools_module, fn_name, fn)
    tools_module.TOOL_DEFINITIONS.append(schema)
    tools_module.dispatch.__globals__[fn_name] = fn   # dispatcher patch

    # Patch dispatcher dict
    def _new_dispatch(name: str, inputs: dict) -> str:
        if name == tool_name:
            return fn(**inputs)
        return tools_module._original_dispatch(name, inputs)

    # Simpler: just add to dispatch dict
    tools_module._DISPATCH_EXTRA[tool_name] = lambda **kw: fn(**kw)

    log_entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "tool": tool_name,
        "status": "deployed",
        "code_lines": len(tool_code.splitlines()),
    }
    with open(BASE_DIR / "evolution_log.jsonl", "a") as f:
        f.write(json.dumps(log_entry) + "\n")

    msg = f"[EVOLVED] Tool '{tool_name}' hot-reloaded. Now available to the agent."
    _LOG.info(msg)
    return msg

# ── Full Cycle ────────────────────────────────────────────

def attempt_self_evolution(task: str, error: str, max_attempts: int = 2) -> str:
    """
    Main entry point. Call when agent task fails.
    Returns status string.

    Args:
        task: The task that failed.
        error: The error message from the failure.
        max_attempts: Maximum number of attempts to evolve a tool (default 2).

    Returns:
        Status string indicating success or failure.
    """
    _LOG.info("[EVOLUTION] Analyzing gap for failed task: %s", task[:60])

    gap = analyze_capability_gap(task, error)
    if not gap.get("name"):
        msg = "[EVOLUTION] No capability gap identified. Logic error only."
        _LOG.info(msg)
        return msg

    name = gap["name"].replace("-", "_").replace(" ", "_").lower()
    desc = gap.get("description", "")
    _LOG.info("[EVOLUTION] Missing capability: '%s' — %s", name, desc)

    for attempt in range(1, max_attempts + 1):
        _LOG.info("[EVOLUTION] Designing tool (attempt %d/%d)", attempt, max_attempts)
        code = design_tool(name, desc, task)

        ok, msg = test_tool_in_sandbox(code, name)
        if ok:
            result = hot_reload_tool(code, name)
            _LOG.info("[EVOLUTION] ✅ %s", result)
            return result
        else:
            _LOG.warning("[EVOLUTION] ❌ Test failed: %s", msg)
            error = msg   # Feed error back for next attempt

    msg = f"[EVOLUTION] Failed to evolve tool '{name}' after {max_attempts} attempts."
    _LOG.error(msg)
    return msg

# ── Load all evolved tools at startup ────────────────────

def load_evolved_tools() -> None:
    """Load all previously evolved tools on startup."""
    count = 0
    for f in EVOLVED_DIR.glob("*.py"):
        if f.name.startswith("test_"):
            continue
        try:
            name = f.stem
            spec = importlib.util.spec_from_file_location(name, f)
            if spec is None:
                _LOG.warning("Could not load module spec for %s", f.name)
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            fn_name = f"execute_{name}"
            if hasattr(module, fn_name) and hasattr(module, "TOOL_SCHEMA"):
                import tools as tools_module
                fn = getattr(module, fn_name)
                setattr(tools_module, fn_name, fn)
                if module.TOOL_SCHEMA not in tools_module.TOOL_DEFINITIONS:
                    tools_module.TOOL_DEFINITIONS.append(module.TOOL_SCHEMA)
                # Register in _DISPATCH_EXTRA for reloads
                tools_module._DISPATCH_EXTRA[name] = lambda **kw: fn(**kw)
                count += 1
            else:
                _LOG.warning("Module %s missing function or schema", f.name)
        except Exception as e:
            _LOG.error("Could not reload %s: %s", f.name, e)
    if count:
        _LOG.info("[EVOLUTION] Reloaded %d evolved tool(s).", count)

# Define public API
__all__: List[str] = [
    "analyze_capability_gap",
    "design_tool",
    "test_tool_in_sandbox",
    "hot_reload_tool",
    "attempt_self_evolution",
    "load_evolved_tools",
]