"""
JARVIS Life State Manager — Persistent Identity
───────────────────────────────────────────────
Manages Dhairya's life state, project goals, and hardware context.
Ensures Jarvis has a consistent "Who am I assisting?" profile.
"""
import json
import os
import subprocess
from pathlib import Path
from datetime import datetime

BASE_DIR = Path.home() / ".jarvis"
LIFE_STATE_FILE = BASE_DIR / "life_state.json"

def get_current_stats():
    """Get real-time hardware context."""
    try:
        # RAM usage
        ram = subprocess.check_output("free -m | awk '/Mem:/ {print $3\"/\"$2\" MB\"}'", shell=True, text=True).strip()
        # Disk usage
        disk = subprocess.check_output("df -h / | awk '/\\// {print $3\"/\"$2}'", shell=True, text=True).strip()
        # Active Windows
        windows = subprocess.check_output("hyprctl clients -j | jq '. | length'", shell=True, text=True).strip()
        return {
            "ram_usage": ram,
            "disk_usage": disk,
            "active_windows": int(windows)
        }
    except Exception:
        return {}

def update_life_state(current_goal: str = None, active_projects: list = None):
    """Update the persistent life state file."""
    # Load existing
    state = {
        "name": "Dhairya",
        "current_goal": "Build JARVIS to supercomputer-level AI",
        "active_projects": ["JARVIS V2"],
        "hardware": {
            "os": "CachyOS Linux",
            "desktop": "Hyprland",
            "gpu": "Intel TigerLake-LP GT2 [Iris Xe Graphics]"
        }
    }
    
    if LIFE_STATE_FILE.exists():
        try:
            with open(LIFE_STATE_FILE, "r") as f:
                state.update(json.load(f))
        except Exception: pass

    # Update dynamic fields
    if current_goal: state["current_goal"] = current_goal
    if active_projects: state["active_projects"] = active_projects
    
    state["system_stats"] = get_current_stats()
    state["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Save
    with open(LIFE_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)
    return state

def get_identity_context() -> str:
    """Returns a string formatted for system prompt injection."""
    if not LIFE_STATE_FILE.exists():
        update_life_state()
    
    try:
        with open(LIFE_STATE_FILE, "r") as f:
            data = json.load(f)
        
        ctx = f"USER: {data['name']}\n"
        ctx += f"CURRENT GOAL: {data['current_goal']}\n"
        ctx += f"ACTIVE PROJECTS: {', '.join(data['active_projects'])}\n"
        ctx += f"HARDWARE: {data['hardware']['os']} | {data['hardware']['gpu']} | RAM: {data.get('system_stats', {}).get('ram_usage', '8GB')}\n"
        ctx += f"STATUS: System has {data.get('system_stats', {}).get('active_windows', 0)} windows open."
        return ctx
    except Exception:
        return "User: Dhairya | Project: JARVIS V2"

if __name__ == "__main__":
    # Self-update when run directly
    s = update_life_state()
    print(f"Life State Updated: {s['last_updated']}")
