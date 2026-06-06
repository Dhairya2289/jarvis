from __future__ import annotations

import json
import logging
import subprocess
import shutil
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import anthropic
from jarvis.config import FCC_BASE_URL, FCC_AUTH_TOKEN, BRAIN_MODEL, PLANS_DIR

_LOG = logging.getLogger(__name__)

client = anthropic.Anthropic(base_url=FCC_BASE_URL, api_key=FCC_AUTH_TOKEN)


def _query(prompt: str, max_tokens: int = 2000) -> str:
    """Query the LLM with a prompt and return the response text.

    Args:
        prompt: The prompt to send to the model.
        max_tokens: Maximum tokens to generate (default 2000).

    Returns:
        The stripped response text.
    """
    r = client.messages.create(
        model=BRAIN_MODEL, max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}]
    )
    return r.content[0].text.strip()


# ── Plan creation ─────────────────────────────────────────

def create_plan(goal: str, deadline: Optional[str] = None, context: str = "") -> Dict[str, Any]:
    """
    Break a goal into milestones → daily tasks.
    Returns plan dict and saves to PLANS_DIR.

    Args:
        goal: The high-level goal to plan for.
        deadline: Optional deadline string in ISO format (YYYY-MM-DD).
                  Defaults to 6 weeks from today.
        context: Additional context for the planning process.

    Returns:
        Dictionary representing the plan.
    """
    deadline_str = deadline or (date.today() + timedelta(weeks=6)).isoformat()
    days_left = (date.fromisoformat(deadline_str) - date.today()).days

    prompt = (
        f"Create a day-by-day study/work plan for this goal.\n\n"
        f"Goal: {goal}\n"
        f"Deadline: {deadline_str} ({days_left} days from today: {date.today()})\n"
        f"Context: {context or 'None'}\n\n"
        f"Requirements:\n"
        f"- Break into weekly milestones\n"
        f"- Each day: 2-3 concrete, actionable tasks (30-90 min each)\n"
        f"- Include rest days (Sunday = review only)\n"
        f"- Escalate intensity as deadline approaches\n\n"
        f"Respond ONLY as JSON (no markdown):\n"
        f'{{"goal": "...", "deadline": "...", "milestones": ['
        f'{{"week": 1, "focus": "...", "days": ['
        f'{{"date": "YYYY-MM-DD", "tasks": ["task1", "task2"]}}]}}]}}'
    )

    raw = _query(prompt)
    # Clean JSON
    raw = raw.replace("```json", "").replace("```", "").strip()
    # Find JSON block
    import re
    m = re.search(r'\{.*\}', raw, re.DOTALL)
    if not m:
        return {"error": "Could not parse plan"}

    plan = json.loads(m.group())
    plan["created"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    plan["completed_tasks"] = []

    # Save
    slug = goal[:30].replace(" ", "_").lower()
    plan_file = PLANS_DIR / f"plan_{slug}_{date.today()}.json"
    plan_file.write_text(json.dumps(plan, indent=2))

    # Sync to Taskwarrior if available
    if shutil.which("task"):
        _sync_to_taskwarrior(plan)

    return plan


def _sync_to_taskwarrior(plan: Dict[str, Any]) -> None:
    """Add tasks to Taskwarrior with due dates.

    Args:
        plan: The plan dictionary containing milestones and tasks.
    """
    try:
        for milestone in plan.get("milestones", []):
            for day in milestone.get("days", []):
                for task_text in day.get("tasks", []):
                    try:
                        subprocess.run(
                            ["task", "add", f"due:{day['date']}",
                             f"project:jarvis.{plan['goal'][:20].replace(' ', '_')}",
                             task_text],
                            capture_output=True,
                            timeout=15,
                        )
                    except subprocess.TimeoutExpired:
                        _LOG.warning("Taskwarrior task add timed out after 15s")
    except Exception as e:
        _LOG.warning("Taskwarrior sync failed: %s", e)


def get_todays_tasks() -> List[str]:
    """Get tasks scheduled for today across all plans.

    Returns:
        List of task strings formatted as '[goal] task'.
    """
    today = date.today().isoformat()
    tasks: List[str] = []

    for plan_file in PLANS_DIR.glob("plan_*.json"):
        try:
            plan = json.loads(plan_file.read_text())
            done = set(plan.get("completed_tasks", []))
            for milestone in plan.get("milestones", []):
                for day in milestone.get("days", []):
                    if day.get("date") == today:
                        for t in day.get("tasks", []):
                            if t not in done:
                                tasks.append(f"[{plan['goal'][:25]}] {t}")
        except Exception as e:
            _LOG.debug("Skipping plan file %s due to error: %s", plan_file, e)
            continue

    return tasks


def mark_done(task_text: str) -> None:
    """Mark a task as completed in its plan file.

    Args:
        task_text: The task string to mark as done.
    """
    for plan_file in PLANS_DIR.glob("plan_*.json"):
        try:
            plan = json.loads(plan_file.read_text())
            if task_text not in plan.get("completed_tasks", []):
                plan.setdefault("completed_tasks", []).append(task_text)
                plan_file.write_text(json.dumps(plan, indent=2))
        except Exception as e:
            _LOG.debug("Failed to mark task done in %s: %s", plan_file, e)
            continue


def get_morning_briefing() -> str:
    """Generate a motivational morning briefing with today's tasks.

    Returns:
        A formatted briefing string.
    """
    tasks = get_todays_tasks()
    if not tasks:
        return "No tasks scheduled for today. Check your plans or create a new goal."

    tasks_str = "\n".join(f"• {t}" for t in tasks)
    prompt = (
        f"Today is {date.today().strftime('%A, %B %d')}.\n"
        f"Generate a sharp, motivational 3-sentence morning briefing for these tasks:\n"
        f"{tasks_str}\n\n"
        f"Then list the tasks clearly. Be concise and energizing."
    )
    return _query(prompt, max_tokens=400)


# Define public API
__all__: List[str] = [
    "create_plan",
    "_sync_to_taskwarrior",
    "get_todays_tasks",
    "mark_done",
    "get_morning_briefing",
]