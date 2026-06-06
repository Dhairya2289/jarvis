"""
JARVIS Bootstrapper v2
─────────────────────
Seeds initial memory with known app layouts, skills,
and injects OS context on first run.
"""
import logging
import subprocess
import json
import os
from pathlib import Path
from jarvis.memory import load_knowledge, save_knowledge
from jarvis.config import BASE_DIR

_log = logging.getLogger(__name__)


def load_user_skills() -> int:
    """Load ~/.jarvis/skills/*.py into tool dispatcher. Returns count loaded."""
    from pathlib import Path
    import importlib.util

    skills_dir = Path.home() / ".jarvis" / "skills"
    if not skills_dir.exists():
        return 0

    loaded = 0
    for skill_file in skills_dir.glob("*.py"):
        if skill_file.name.startswith("__"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(
                f"user_skill_{skill_file.stem}", skill_file
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            if hasattr(mod, "run"):
                from jarvis.tools import register_tool
                register_tool(skill_file.stem, mod.run)
                loaded += 1
                _log.info("Loaded user skill: %s", skill_file.stem)
        except Exception as e:
            _log.error("[SKILLS] Failed to load %s: %s", skill_file.name, e)

    return loaded

def bootstrap():
    _log.info("JARVIS Bootstrap v2 — Initializing knowledge base...")
    k = load_knowledge()

    # ── App Coordinates ────────────────────────────────────
    # These are normalized for 1920x1080. Jarvis will learn
    # real coordinates via remember_gui over time.
    defaults = {
        "firefox": {
            "address_bar":    {"x": 640, "y": 45},
            "new_tab_button": {"x": 1100, "y": 45},
            "close_tab":      {"x": 1080, "y": 45},
        },
        "foot":    {"center":         {"x": 960,  "y": 540}},
        "kitty":   {"center":         {"x": 960,  "y": 540}},
        "code":    {
            "terminal_toggle": {"x": 960, "y": 900},
            "file_explorer":   {"x": 20,  "y": 300},
            "search":          {"x": 20,  "y": 100},
        },
        "obsidian": {
            "search":    {"x": 250, "y": 30},
            "new_note":  {"x": 15,  "y": 60},
        },
        "anki": {
            "add_card": {"x": 200, "y": 80},
            "sync":     {"x": 400, "y": 80},
        },
    }
    for app, elements in defaults.items():
        k["app_layouts"].setdefault(app, {}).update(elements)
    _log.info("Injected %s app coordinates", sum(len(v) for v in defaults.values()))

    # ── Pre-built Skills ───────────────────────────────────
    skills = {
        "deep_research": [
            "gemini_search: search the topic",
            "multi_scrape: scrape top 3 results",
            "delegate_swarm: researcher + writer agents synthesize",
            "obsidian_note: store findings",
        ],
        "code_and_deploy": [
            "codex: generate code",
            "sandboxed_bash: run tests",
            "deploy_to_system: if tests pass",
            "desktop_notification: notify completion",
        ],
        "study_from_pdf": [
            "read_file: read PDF path",
            "gemini_search: look up related concepts",
            "anki_add: create flashcards for key concepts",
            "obsidian_note: save summary",
        ],
        "system_diagnostic": [
            "os_mind_meld: read system state",
            "bash: journalctl -p err -n 20",
            "bash: df -h && free -h",
        ],
        "morning_routine": [
            "morning_briefing: get today's tasks",
            "speak: read briefing aloud",
            "desktop_notification: show task count",
        ],
    }
    for name, steps in skills.items():
        k["learned_skills"][name] = {"steps": steps}
    _log.info("Injected %s macro skills", len(skills))

    # ── Pre-seeded Lessons ────────────────────────────────
    initial_lessons = [
        {
            "context": "CachyOS Hyprland session",
            "mistake": "Using x11 tools (xdotool, scrot) on Wayland",
            "fix":     "Use ydotool for input, grim for screenshots, wl-copy/wl-paste for clipboard"
        },
        {
            "context": "FCC Proxy model routing",
            "mistake": "Sending all tasks to the same model",
            "fix":     "Route code to deepseek-r1, research to gemini-2.5-pro, speed tasks to llama-3.1-8b"
        },
        {
            "context": "Ansible/bash on CachyOS",
            "mistake": "Using apt-get commands",
            "fix":     "CachyOS uses pacman / yay for package management"
        },
        {
            "context": "Python subprocess on CachyOS",
            "mistake": "Assuming python resolves to python3",
            "fix":     "Always use python3 explicitly on Arch-based systems"
        },
    ]
    for lesson in initial_lessons:
        k["lessons"].append({**lesson})
    _log.info("Injected %s initial lessons", len(initial_lessons))

    # ── User preferences ──────────────────────────────────
    k["user_prefs"].update({
        "os":          "CachyOS Linux",
        "compositor":  "Hyprland",
        "terminal":    "foot",
        "shell":       "zsh",
        "package_mgr": "pacman/yay",
        "editor":      "nvim/code",
        "notes_app":   "obsidian",
        "flashcards":  "anki",
    })
    _log.info("Injected OS context preferences")

    # ── Read shell aliases ────────────────────────────────
    for rc in [Path.home()/".zshrc", Path.home()/".bashrc"]:
        if rc.exists():
            aliases = [
                l.strip() for l in rc.read_text(errors="ignore").splitlines()
                if l.strip().startswith("alias ")
            ][:20]
            if aliases:
                k["user_prefs"]["shell_aliases"] = aliases
                _log.info("Learned %s shell aliases from %s", len(aliases), rc.name)
            break

    save_knowledge(k)
    _log.info("Bootstrap complete. Knowledge stored at: %s/knowledge.json", BASE_DIR)

if __name__ == "__main__":
    bootstrap()
