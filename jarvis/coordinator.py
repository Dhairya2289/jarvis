"""
coordinator.py — Multi-Agent Task Coordinator
───────────────────────────────────────────────
Inspired by Claude's coordinator mode.

Pipeline
--------
1. decompose(task)    → list[Subtask]   (keyword-based, no LLM)
2. execute_parallel(subtasks) → list[Subtask]  (ThreadPoolExecutor)
3. merge(results)     → str             (markdown summary)
4. run(task)          → CoordinatorResult (full pipeline)
"""

from __future__ import annotations

import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from typing import Any

_LOG = logging.getLogger(__name__)

# ── Dataclasses ────────────────────────────────────────────


@dataclass
class Subtask:
    """A single piece of work assigned to a specialist."""
    id: str
    description: str
    specialist: str = "agent"   # module / specialist name
    status: str = "pending"     # pending | running | done | error
    result: str = ""


@dataclass
class CoordinatorResult:
    """Outcome of a full coordinator run."""
    original_task: str
    subtasks: list[Subtask]
    merged_result: str
    duration_ms: int


# ── Coordinator ─────────────────────────────────────────────


class Coordinator:
    """
    Multi-agent task coordinator.

    Breaks complex tasks into subtasks, executes them in parallel,
    and merges results into a unified markdown response.
    """

    def __init__(self) -> None:
        self._specialist_map: dict[str, str] = {
            # Maps keyword → specialist name (matches context_engine.CATEGORY_SPECIALISTS)
            "code":    "agent",
            "script":  "agent",
            "program": "agent",
            "write":   "agent",
            "debug":   "agent",
            "system":  "tools",
            "config":  "tools",
            "bash":    "tools",
            "shell":   "tools",
            "process": "tools",
            "cpu":     "tools",
            "memory":  "tools",
            "disk":    "tools",
        }

    # ── Step 1: Decompose ──────────────────────────────────

    def decompose(self, task: str) -> list[Subtask]:
        """
        Break a task into subtasks using simple keyword heuristics.

        Splitting rules (no LLM):
        • "and" / newline          → split into multiple subtasks
        • "compare", "vs", "versus" → two subtasks
        • "summarize", "conclusion" → single subtask
        • Otherwise                → single subtask
        """
        task = task.strip()
        if not task:
            return []

        subtask_texts: list[str] = []

        # Check for compare / versus
        compare_markers = (" compare ", " vs ", " versus ", " compare ")
        has_compare = any(m in task.lower() for m in compare_markers)
        if has_compare:
            # Try to split on " vs " / " versus "
            import re
            parts = re.split(r'\s+vs\.?\s+|\s+versus\s+|\s+compare\s+to?\s+', task, flags=re.IGNORECASE)
            if len(parts) >= 2:
                subtask_texts = [p.strip() for p in parts if p.strip()]
            else:
                # Fallback: split on " and "
                subtask_texts = [s.strip() for s in re.split(r'\s+and\s+', task, flags=re.IGNORECASE) if s.strip()]

        # Check for multi-sentence / "and" split
        elif ' and ' in task.lower() or '\n' in task:
            import re
            parts = re.split(r'\s+and\s+|\n+', task, flags=re.IGNORECASE)
            subtask_texts = [s.strip() for s in parts if s.strip()]

        else:
            subtask_texts = [task]

        # Build Subtask objects
        subtasks: list[Subtask] = []
        for i, desc in enumerate(subtask_texts, 1):
            specialist = self._route_to_specialist(desc)
            subtasks.append(Subtask(
                id=f"sub_{uuid.uuid4().hex[:8]}",
                description=desc,
                specialist=specialist,
                status="pending",
            ))

        return subtasks

    def _route_to_specialist(self, description: str) -> str:
        """Route a description to a specialist based on keyword heuristics."""
        desc_lower = description.lower()
        # Try to reuse context_engine specialists if available
        try:
            from jarvis.context_engine import CATEGORY_SPECIALISTS
            # Quick keyword check against known categories
            for kw, specialist in self._specialist_map.items():
                if kw in desc_lower:
                    return specialist
            # Fallback to context_engine
            from jarvis.context_engine import classify_intent
            intent = classify_intent(description)
            return intent.specialist
        except ImportError:
            pass

        # Fallback: simple keyword map
        for kw, specialist in self._specialist_map.items():
            if kw in desc_lower:
                return specialist
        return "agent"

    # ── Step 2: Execute parallel ────────────────────────────

    def execute_parallel(self, subtasks: list[Subtask]) -> list[Subtask]:
        """
        Run subtasks concurrently using ThreadPoolExecutor.

        Each subtask calls its specialist:
        • "agent"  → run_agent(subtask.description)
        • "tools"  → dispatch_tool("bash", {"command": subtask.description})
        • _        → run_agent(subtask.description)  (fallback)
        """
        results: list[Subtask] = []

        def run_one(st: Subtask) -> Subtask:
            st.status = "running"
            try:
                if st.specialist == "tools":
                    try:
                        from jarvis.tools import dispatch_tool
                        # Extract a bash command from description heuristically
                        result = self._execute_tools_task(st.description)
                        st.result = result
                    except Exception as exc:
                        st.result = f"[ERROR] {exc}"
                else:
                    result = self._execute_agent_task(st.description)
                    st.result = result
                st.status = "done"
            except Exception as exc:
                st.status = "error"
                st.result = f"[ERROR] {exc}"
            return st

        with ThreadPoolExecutor(max_workers=min(len(subtasks), 4)) as pool:
            futures = {pool.submit(run_one, st): st for st in subtasks}
            for future in as_completed(futures):
                results.append(future.result())

        # Preserve original ordering by matching IDs
        id_order = {st.id: i for i, st in enumerate(subtasks)}
        results.sort(key=lambda st: id_order[st.id])
        return results

    def _execute_agent_task(self, description: str) -> str:
        """Run description through the main agent (async → sync wrapper)."""
        try:
            from jarvis.agent import run_agent
            import asyncio
            # run_agent is async; run in event loop
            try:
                loop = asyncio.get_running_loop()
                # Already in async context — cannot block, run concurrently
                import concurrent.futures
                def _sync():
                    return asyncio.run(run_agent(description))
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as tp:
                    future = tp.submit(_sync)
                    return future.result(timeout=120)
            except RuntimeError:
                # No running loop
                return asyncio.run(run_agent(description))
        except ImportError:
            return "[COORDINATOR] agent module not available"
        except Exception as exc:
            return f"[ERROR] {exc}"

    def _execute_tools_task(self, description: str) -> str:
        """Run a tools-specialist subtask via dispatch_tool bash."""
        try:
            from jarvis.tools import dispatch_tool
            return dispatch_tool("bash", {"command": description})
        except ImportError:
            return "[COORDINATOR] tools module not available"
        except Exception as exc:
            return f"[ERROR] {exc}"

    # ── Step 3: Merge ──────────────────────────────────────

    @staticmethod
    def merge(subtasks: list[Subtask]) -> str:
        """
        Combine subtask results into a single markdown response.
        """
        if not subtasks:
            return "No results to merge."

        lines = ["# Results\n"]

        for i, st in enumerate(subtasks, 1):
            lines.append(f"## Subtask {i}: {st.description}\n")
            status_tag = f"[{st.status.upper()}]" if st.status in ("pending", "running", "error") else ""
            lines.append(f"{status_tag} {st.result}\n")

        # Summary line
        done = [st for st in subtasks if st.status == "done"]
        errors = [st for st in subtasks if st.status == "error"]
        lines.append("# Summary\n")
        if done:
            lines.append(f"✅ {len(done)}/{len(subtasks)} subtask(s) completed successfully.")
        if errors:
            lines.append(f"⚠️ {len(errors)} subtask(s) encountered errors.")

        return "\n".join(lines)

    # ── Step 4: Full pipeline ──────────────────────────────

    def run(self, task: str) -> CoordinatorResult:
        """
        Execute the full decompose → execute → merge pipeline.

        Returns a CoordinatorResult with timing information.
        """
        start = time.time()
        subtasks = self.decompose(task)
        if not subtasks:
            return CoordinatorResult(
                original_task=task,
                subtasks=[],
                merged_result="No subtasks generated for this task.",
                duration_ms=int((time.time() - start) * 1000),
            )
        executed = self.execute_parallel(subtasks)
        merged = self.merge(executed)
        duration_ms = int((time.time() - start) * 1000)
        return CoordinatorResult(
            original_task=task,
            subtasks=executed,
            merged_result=merged,
            duration_ms=duration_ms,
        )