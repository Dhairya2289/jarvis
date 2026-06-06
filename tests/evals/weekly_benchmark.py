"""Weekly evaluation harness for JARVIS."""
import asyncio
import json
from datetime import datetime
from jarvis.agent import run_agent
from jarvis.obsidian_brain import write_note

BENCHMARK_TASKS = [
    ("What's my current CPU usage?", ["cpu", "%"]),
    ("Open terminal", ["launched", "alacritty", "terminal", "foot"]),
    ("Search files for jarvis", ["found", ".py", "search"]),
    ("What am I working on?", ["dhairya", "jarvis", "desktop", "window"]),
    ("Set volume to 50%", ["volume", "50", "pactl"]),
    ("Summarize today's Obsidian notes", ["note", "today", "obsidian"]),
    ("Create a todo: review PR tomorrow", ["created", "todo", "task"]),
    ("What browser am I using?", ["firefox", "chromium", "browser"]),
    ("Lock the screen", ["locked", "suspend", "hyprctl"]),
    ("Explain what JARVIS is", ["assistant", "ai", "jarvis", "system"]),
]


async def run_weekly_eval():
    results = []
    for task, keywords in BENCHMARK_TASKS:
        try:
            result = await asyncio.wait_for(run_agent(task), timeout=60.0)
            passed = any(kw.lower() in result.lower() for kw in keywords)
        except Exception:
            result = "[ERROR]"
            passed = False
        results.append({"task": task, "passed": passed, "result": result[:120]})

    score = sum(r["passed"] for r in results) / len(results)

    note = f"# Weekly Eval — {datetime.now().strftime('%Y-%m-%d')}\n\n"
    note += f"**Score: {score:.0%}**\n\n"
    for r in results:
        icon = "✅" if r["passed"] else "❌"
        note += f"{icon} {r['task']}\n"
        note += f"   → {r['result']}\n\n"

    write_note(f"evals/eval_{datetime.now():%Y%m%d}.md", note)
    return score, results


if __name__ == "__main__":
    score, results = asyncio.run(run_weekly_eval())
    print(f"Score: {score:.0%}")
