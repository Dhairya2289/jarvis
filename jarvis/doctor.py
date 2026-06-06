"""
JARVIS Preflight Doctor — System Health Check
─────────────────────────────────────────────
Checks all 12+ subsystems to ensure Jarvis is healthy.
"""
import os
import shutil
import subprocess
import requests
import json
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.live import Live

console = Console()

BASE_DIR = Path.home() / ".jarvis"
VENV_PYTHON = Path.home() / ".jarvis_app/venv/bin/python"

def check_url(name, url):
    try:
        r = requests.get(url, timeout=2)
        if r.status_code < 500:
            return "✅ Reachable", "green"
        return f"❌ Error {r.status_code}", "red"
    except Exception:
        return "❌ Unreachable", "red"

def check_command(name, cmd):
    if shutil.which(cmd):
        return "✅ Installed", "green"
    return "❌ Missing", "red"

def check_service(name):
    try:
        res = subprocess.run(["systemctl", "--user", "is-active", name], 
                             capture_output=True, text=True, timeout=15)
        status = res.stdout.strip()
        if status == "active":
            return "✅ Running", "green"
        return f"❌ {status}", "yellow"
    except subprocess.TimeoutExpired:
        return "⚠️ Timeout", "yellow"
    except Exception:
        return "⚠️ Unknown", "yellow"

def run_doctor():
    table = Table(title="👨‍⚕️ JARVIS Preflight Health Check", show_header=True, header_style="bold magenta")
    table.add_column("Subsystem", style="dim")
    table.add_column("Status")
    table.add_column("Details")

    # 1. Infrastructure
    fcc_status, fcc_color = check_url("FCC Proxy", "http://127.0.0.1:8082")
    table.add_row("FCC Proxy", fcc_status, "Core routing engine")
    
    api_status, api_color = check_url("FastAPI Server", "http://127.0.0.1:8090/health")
    table.add_row("HTTP API", api_status, "Remote control bridge")
    
    ollama_status, ollama_color = check_url("Ollama API", "http://127.0.0.1:11434")
    table.add_row("Ollama", ollama_status, "Local L1 inference")
    
    # 2. Networking
    tailscale_active = "❌ Inactive"
    ts_color = "red"
    if shutil.which("tailscale"):
        try:
            res = subprocess.run(["tailscale", "status"], capture_output=True, text=True, timeout=15)
            if "logged out" not in res.stdout:
                tailscale_active = "✅ Active"
                ts_color = "green"
        except subprocess.TimeoutExpired:
            tailscale_active = "⚠️ Timeout"
            ts_color = "yellow"
        except Exception: pass
    table.add_row("Tailscale", tailscale_active, "Remote secure access")

    # 3. Desktop / OS
    hypr_active = "✅ Active" if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") else "❌ Not found"
    hypr_color = "green" if hypr_active.startswith("✅") else "red"
    table.add_row("Hyprland IPC", hypr_active, "Window management")
    
    # 4. Storage & Memory
    chroma_path = BASE_DIR / "chroma_db"
    chroma_status = "✅ OK" if chroma_path.exists() else "⚠️ Not initialized"
    table.add_row("ChromaDB", chroma_status, f"{len(list(chroma_path.glob('*')))} files indexed")
    
    # 5. External Tools
    anki_status, anki_color = check_url("AnkiConnect", "http://127.0.0.1:8765")
    table.add_row("AnkiConnect", anki_status, "Flashcard sync (requires Anki open)")
    
    # 6. Capabilities
    vision_ready = "✅ Ready" if Path("Projects/Jarvis/V2/vision_agent.py").exists() else "❌ Missing"
    table.add_row("Vision Engine", vision_ready, "Screenshot-to-coordinate mapping")

    # 7. Services
    table.add_section()
    for svc in ["jarvis-daemon", "jarvis-telegram", "jarvis-hud", "jarvis-clip", "jarvis-api", "jarvis-queue"]:
        status, color = check_service(svc)
        table.add_row(f"Service: {svc}", status, "Systemd user unit")

    console.print(table)
    
    # Summary
    if any(c == "red" for c in [fcc_color, ollama_color, hypr_color]):
        console.print("\n[bold red]✖ System Critical issues found! Fix them before proceeding.[/bold red]")
    else:
        console.print("\n[bold green]✔ All systems operational. Jarvis is ready for Phase 1.[/bold green]")

if __name__ == "__main__":
    run_doctor()
