"""
JARVIS CLI v3 — Rich Terminal Interface
──────────────────────────────────────────────────────────────
Usage:
  jarvis-v3                               # Interactive mode
  jarvis-v3 "your task"                   # One-shot
  jarvis-v3 --doctor                      # Run system health check
  jarvis-v3 --voice                       # Start voice assistant
  jarvis-v3 --debate "q"                  # Multi-model debate
  jarvis-v3 --plan "goal"                 # Create a plan
  jarvis-v3 --morning                     # Morning briefing
  jarvis-v3 --hud                         # Launch HUD server
  jarvis-v3 workflow run <file>           # Run a workflow
"""

import argparse
import asyncio
import os
import sys
from typing import Optional

try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.live import Live
    from rich.table import Table
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.styles import Style
    PTK_AVAILABLE = True
except ImportError:
    PTK_AVAILABLE = False

BANNER = """
      ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
      ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
      ██║███████║██████╔╝██║   ██║██║███████╗
 ██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
 ╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║
  ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝
        Autonomous AI Operating System v3.0
"""


console = Console() if RICH_AVAILABLE else None
session = (
    PromptSession(style=Style.from_dict({"prompt": "ansicyan bold"}))
    if PTK_AVAILABLE
    else None
)


def print_banner():
    if not RICH_AVAILABLE:
        print(BANNER)
        return
    console.print(Panel(BANNER, style="bold cyan", expand=False))  # type: ignore
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_row("FCC Proxy", "[green]●[/green] Running")
    table.add_row(
        "Voice",
        "[yellow]○[/yellow] Run --voice to start",
    )
    table.add_row("Daemon", "[green]●[/green] Active" if _daemon_running() else "[yellow]○[/yellow] Stopped")
    console.print(table)  # type: ignore
    console.print()  # type: ignore


def _daemon_running() -> bool:
    return os.path.exists(os.path.expanduser("~/.jarvis/daemon.pid"))


async def run_task(task: str) -> str:
    status_lines: list = []
    full_text = ""

    def on_status(msg: str):
        status_lines.append(f"→ {msg}")
        if len(status_lines) > 5:
            status_lines.pop(0)
        _render()

    def on_token(delta: str):
        nonlocal full_text
        full_text += delta
        _render()

    def _render():
        if not RICH_AVAILABLE or live is None:
            return
        content = "\n".join(status_lines)
        if full_text:
            content += "\n\n" + full_text
        live.update(  # type: ignore
            Panel(
                content,
                title="[yellow]⚙ Executing[/yellow]",
                border_style="yellow",
            )
        )

    from jarvis.agent import run_agent

    if not RICH_AVAILABLE:
        return await run_agent(task, status_callback=on_status, token_callback=on_token)

    with Live(
        Panel("Initializing...", title="[yellow]⚙ Executing[/yellow]", border_style="yellow"),
        refresh_per_second=10,
        console=console,
    ) as live:
        result = await run_agent(task, status_callback=on_status, token_callback=on_token)
    return result


def _run_sync(coro):
    return asyncio.run(coro)


async def interactive_loop():
    print_banner()
    print("Commands: /quit  /clear  /voice  /debate <q>  /plan <goal>  /today  /stats  /doctor")
    print()

    while True:
        try:
            if session:
                raw = session.prompt("Jarvis> ").strip()
            else:
                raw = input("Jarvis> ").strip()
            if not raw:
                continue

            if raw.lower() in ["/quit", "/exit", "exit", "quit"]:
                print("Session terminated.")
                break

            if raw.lower() == "/clear":
                os.system("clear")
                print_banner()
                continue

            if raw.lower() == "/today":
                print("[today] No planner module yet. Use /plan to create a goal.")
                continue

            if raw.lower() == "/stats":
                try:
                    from jarvis.orchestrator import get_routing_report
                    report = get_routing_report()
                    if RICH_AVAILABLE:
                        console.print(Markdown(report))  # type: ignore
                    else:
                        print(report)
                except Exception as e:
                    print(f"Error: {e}")
                continue

            if raw.lower().startswith("/debate "):
                q = raw[8:].strip()
                print("⚖️ Starting debate...")
                try:
                    from jarvis.debate import run_debate
                    result = await run_debate(q)
                    if RICH_AVAILABLE:
                        console.print(Panel(Markdown(result), title="⚖️ Debate Result", border_style="cyan"))  # type: ignore
                    else:
                        print(result)
                except Exception as e:
                    print(f"Debate error: {e}")
                continue

            if raw.lower().startswith("/plan "):
                goal = raw[6:].strip()
                print("📅 Building your plan...")
                print(f"Goal: {goal}")
                continue

            if raw.lower() == "/voice":
                print("🎙️ Voice assistant not yet ported to V3.")
                continue

            result = await run_task(raw)
            if RICH_AVAILABLE:
                console.print(  # type: ignore
                    Panel(Markdown(result), title="[bold green]✅ Result[/bold green]", border_style="green")
                )
                console.print()  # type: ignore
            else:
                print(result)

        except KeyboardInterrupt:
            print("Cancelled.")
        except EOFError:
            break
        except Exception as e:
            print(f"Error: {e}")


def doctor():
    """Print provider health report."""
    from jarvis.api_manager import get_manager

    async def _check():
        async with get_manager() as mgr:
            report = await mgr.doctor()
            if RICH_AVAILABLE:
                table = Table(title="Provider Health", header_style="bold cyan")
                table.add_column("Provider")
                table.add_column("Configured")
                table.add_column("Reachable")
                table.add_column("Models")
                for name, data in report.items():
                    cfg = "✅" if data["configured"] else "❌"
                    reach = "✅" if data["reachable"] else "❌"
                    models = ", ".join(data["models"])
                    table.add_row(name, cfg, reach, models)
                console.print(table)  # type: ignore
            else:
                print("Provider Health Report")
                for name, data in report.items():
                    print(f"  {name}: configured={data['configured']} reachable={data['reachable']} models={data['models']}")

    _run_sync(_check())


def main():
    parser = argparse.ArgumentParser(description="JARVIS CLI v3")
    parser.add_argument("task", nargs="?", help="Task to execute")
    parser.add_argument("--doctor", action="store_true", help="Run system health check")
    parser.add_argument("--voice", action="store_true", help="Start voice assistant")
    parser.add_argument("--debate", metavar="Q", help="Multi-model debate")
    parser.add_argument("--plan", metavar="GOAL", help="Create long-horizon plan")
    parser.add_argument("--morning", action="store_true", help="Morning briefing")
    parser.add_argument("--hud", action="store_true", help="Launch HUD server")
    parser.add_argument("--vision", action="store_true", help="Capture screen and ask vision model")
    parser.add_argument("--workflow", nargs="*", help="Workflow subcommand")
    parser.add_argument("--loop", action="store_true", help="Start the unified JARVIS agent loop")
    args = parser.parse_args()

    if args.doctor:
        doctor()
        return

    if args.hud:
        try:
            from jarvis.gui_server import run_server
            run_server()
        except Exception as e:
            print(f"HUD error: {e}")
        return

    if args.vision:
        try:
            from jarvis.vision_tool import capture_and_ask
            print("📸 Capturing screen...")
            result = _run_sync(capture_and_ask("Describe what you see on screen."))
            print(result)
        except Exception as e:
            print(f"Vision error: {e}")
        return

    if args.debate:
        print_banner() if RICH_AVAILABLE else None
        try:
            result = _run_sync(run_debate(args.debate))  # type: ignore
            if RICH_AVAILABLE:
                console.print(Panel(Markdown(result), title="⚖️ Debate", border_style="cyan"))  # type: ignore
            else:
                print(result)
        except Exception as e:
            print(f"Error: {e}")
        return

    if args.morning:
        print("☀️ Morning briefing not yet implemented in V3.")
        return

    if args.loop:
        print_banner() if RICH_AVAILABLE else None
        async def run_loop():
            async with get_manager() as mgr:
                from jarvis.core.loop import JARVISLoop
                async with JARVISLoop() as loop:
                    result = await loop.run_once(" ".join(args.task) if args.task else "hello", source="cli")
                    if RICH_AVAILABLE:
                        console.print(Panel(Markdown(result), border_style="cyan"))  # type: ignore
                    else:
                        print(result)
        _run_sync(run_loop())
        return

    if args.task:
        print_banner() if RICH_AVAILABLE else None
        result = _run_sync(run_task(args.task))
        if RICH_AVAILABLE:
            console.print(Panel(Markdown(result), border_style="green"))  # type: ignore
        else:
            print(result)
        return

    # Default: interactive
    _run_sync(interactive_loop())


if __name__ == "__main__":
    main()
