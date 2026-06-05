from __future__ import annotations

import asyncio
import logging
import time
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from jarvis_v3.config import MODELS
from jarvis_v3.api_manager import call_with_rotation

_LOG = logging.getLogger(__name__)

SUB_MODELS = {
    "researcher": "research",
    "coder":      "code",
    "operator":   "speed",
    "reviewer":   "logic",
    "critic":     "logic",
    "writer":     "logic",
}

ROLE_PROMPTS = {
    "researcher": "You are a research specialist. Find facts, cite sources, be thorough.",
    "coder":      "You are a code expert. Write clean, working code. Always include error handling.",
    "operator":   "You are a fast executor. Run tasks, report results. Be direct and concise.",
    "reviewer":   "You are a quality reviewer. Check accuracy and completeness. Flag errors.",
    "critic":     "You are a harsh critic. Find flaws, gaps, and improvements. Be specific.",
    "writer":     "You are a clear writer. Synthesize information into readable prose.",
}

# ── Single sub-agent ──────────────────────────────────────

def run_sub_agent(role: str, task: str, context: str = "", depth: int = 1) -> Dict[str, Any]:
    """
    Run a sub-agent with a full tool-use loop.
    Returns {role, result, success, time_s}

    Args:
        role: The agent role (e.g., 'researcher', 'coder').
        task: The task description for the agent.
        context: Optional context from previous agents.
        depth: Recursion depth to prevent infinite delegation (default 1).

    Returns:
        Dictionary with keys: role, result, success, time_s.
    """
    if depth > 3:
        result = {"role": role, "result": "[ERROR] Agent max depth reached.", "success": False, "time_s": 0}
        _LOG.warning("Agent max depth reached for role %s", role)
        return result

    task_type = SUB_MODELS.get(role, "logic")
    system = ROLE_PROMPTS.get(role, "You are an AI assistant.")
    
    # Discourage further delegation
    if depth > 1:
        system += " You are currently a sub-agent. Do NOT use delegate_swarm; execute tasks directly using other tools."

    # Build initial message
    full_prompt = task
    if context:
        full_prompt = f"Context from previous agents:\n{context}\n\nYour task: {task}"

    messages = [{"role": "user", "content": [{"type": "text", "text": full_prompt}]}]
    
    start = time.time()
    iteration = 0
    max_iter = 10
    final = ""

    try:
        # Import inside function to avoid circular dependencies
        from tools import TOOL_DEFINITIONS, dispatch_tool
        
        # Filter out delegation tool for sub-agents
        available_tools = TOOL_DEFINITIONS
        if depth >= 2:
            available_tools = [t for t in TOOL_DEFINITIONS if t["name"] != "delegate_swarm"]

        while iteration < max_iter:
            iteration += 1
            
            response = call_with_rotation(
                task=task, task_type=task_type,
                messages=messages, system=system,
                tools=available_tools
            )

            # Handle cached result
            if isinstance(response, str):
                final = response
                break

            messages.append({"role": "assistant", "content": response.content})
            tool_calls = [b for b in response.content if b.type == "tool_use"]
            text_blocks = [b for b in response.content if b.type == "text"]

            if text_blocks:
                final += text_blocks[0].text
            
            if not tool_calls:
                break

            # Execute tools
            tool_results = []
            for tool in tool_calls:
                _LOG.debug("[SWARM:%s] 🔧 %s", role.upper(), tool.name)
                out = dispatch_tool(tool.name, tool.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool.id,
                    "content": str(out)[:8000]
                })
            
            messages.append({"role": "user", "content": tool_results})

        result = {"role": role, "result": final.strip(), "success": True,
                "time_s": round(time.time() - start, 1)}
        _LOG.info("Sub-agent %s completed in %.1fs", role, result["time_s"])
        return result

    except Exception as e:
        result = {"role": role, "result": f"[ERROR] {e}", "success": False,
                "time_s": round(time.time() - start, 1)}
        _LOG.error("Sub-agent %s failed: %s", role, e)
        return result

# ── Parallel swarm ────────────────────────────────────────

def execute_swarm(delegations: List[Dict[str, str]], depth: int = 1) -> str:
    """
    Run all delegations in parallel, then run a Critic pass.
    delegations = [{"role": "...", "task": "..."}]

    Args:
        delegations: List of delegation dictionaries with 'role' and 'task'.
        depth: Recursion depth (default 1).

    Returns:
        Formatted string of agent outputs, optionally followed by critic review.
    """
    with ThreadPoolExecutor(max_workers=len(delegations)) as pool:
        futures = {
            pool.submit(run_sub_agent, d["role"], d["task"], depth=depth + 1): d
            for d in delegations
        }
        outputs = []
        for future in as_completed(futures):
            outputs.append(future.result())

    # Format outputs
    report = "\n\n".join(
        f"**{o['role'].upper()}** ({o['time_s']}s):\n{o['result']}"
        for o in sorted(outputs, key=lambda x: x["role"])
    )

    # Critic pass — catch errors before returning
    critic_result = run_sub_agent(
        "critic",
        "Review all agent outputs below. "
        "Point out any errors, gaps, or inconsistencies in 2-3 sentences. "
        "If everything looks correct, say 'APPROVED'.",
        context=report,
        depth=depth + 1
    )

    if "APPROVED" in critic_result["result"]:
        _LOG.info("Swarm execution approved by critic")
        return report
    else:
        _LOG.info("Swarm execution criticized: %s", critic_result["result"][:100])
        return f"{report}\n\n**🔍 CRITIC REVIEW:**\n{critic_result['result']}"

# ── Sequential (chained) swarm ─────────────────────────────

def execute_chain(steps: List[Dict[str, str]], depth: int = 1) -> str:
    """
    Run agents sequentially, each receiving prior agents' outputs as context.
    steps = [{"role": "researcher", "task": "..."}, {"role": "coder", "task": "..."}]

    Args:
        steps: List of step dictionaries with 'role' and 'task'.
        depth: Recursion depth (default 1).

    Returns:
        Formatted string of sequential agent outputs.
    """
    context = ""
    results = []

    for step in steps:
        _LOG.info("[SWARM CHAIN] → %s", step['role'].upper())
        out = run_sub_agent(step["role"], step["task"], context=context, depth=depth + 1)
        results.append(f"**{out['role'].upper()}:**\n{out['result']}")
        context += f"\n{out['role']} output:\n{out['result'][:800]}\n"

    return "\n\n".join(results)

# ── Smart delegation ──────────────────────────────────────

def smart_delegate(task: str, depth: int = 1) -> str:
    """
    Automatically decide parallel vs chain based on task dependencies.
    - Independent subtasks → parallel
    - Code-then-review type tasks → chain

    Args:
        task: The task description to delegate.
        depth: Recursion depth (default 1).

    Returns:
        Result string from the chosen delegation strategy.
    """
    t = task.lower()
    
    # If already a sub-agent, don't delegate further
    if depth >= 2:
        result = run_sub_agent("operator", task, depth=depth)["result"]
        _LOG.debug("Smart delegate at depth %d returning operator result", depth)
        return result

    # Code tasks: research → code → review (must be sequential)
    if any(k in t for k in ["build","create","implement","write code","develop"]):
        _LOG.info("Smart delegate choosing chain for code task: %s", task[:50])
        return execute_chain([
            {"role": "researcher", "task": f"Research best approach for: {task}"},
            {"role": "coder",      "task": f"Implement: {task}"},
            {"role": "reviewer",   "task": "Review the code above for correctness and quality."},
        ], depth=depth)

    # Research tasks: multiple sources in parallel
    if any(k in t for k in ["research","compare","analyze","investigate"]):
        _LOG.info("Smart delegate choosing swarm for research task: %s", task[:50])
        return execute_swarm([
            {"role": "researcher", "task": task},
            {"role": "coder",      "task": f"Find code examples related to: {task}"},
        ], depth=depth)

    # Default: single operator
    _LOG.info("Smart delegate choosing operator for task: %s", task[:50])
    return run_sub_agent("operator", task, depth=depth)["result"]


# Define public API
__all__: List[str] = [
    "run_sub_agent",
    "execute_swarm",
    "execute_chain",
    "smart_delegate",
]