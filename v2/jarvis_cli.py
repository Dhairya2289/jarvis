"""
JARVIS CLI v2 — Rich Terminal Interface
Usage:
  python jarvis_cli.py                    # Interactive mode
  python jarvis_cli.py "your task"        # One-shot
  python jarvis_cli.py --voice            # Start voice assistant
  python jarvis_cli.py --debate "q"       # Multi-model debate
  python jarvis_cli.py --plan "goal"      # Create a plan
  python jarvis_cli.py --morning          # Today's briefing
"""
import sys
import os
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.live import Live
from rich.text import Text
from rich.table import Table
from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style
from agent import run_agent

console = Console()
session = PromptSession(style=Style.from_dict({"prompt": "ansicyan bold"}))

BANNER = """
      ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗
      ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝
      ██║███████║██████╔╝██║   ██║██║███████╗
 ██   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║
 ╚█████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║
  ╚════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝
        Autonomous AI Operating System v2.0
"""

def print_banner():
    console.print(Panel(BANNER, style="bold cyan", expand=False))
    # Show quick status
    table = Table(show_header=False, box=None, padding=(0,1))
    table.add_row("FCC Proxy", "[green]●[/green] Running")
    table.add_row("Voice",     "[yellow]○[/yellow] Run --voice to start")
    table.add_row("Daemon",    "[green]●[/green] Active" if
                  __import__("pathlib").Path.home().joinpath(".jarvis/daemon.pid").exists()
                  else "[yellow]○[/yellow] Run daemon.py")
    console.print(table)
    console.print()

def run_task(task: str) -> str:
    status_lines = []
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
        content = "\n".join(status_lines)
        if full_text:
            content += "\n\n" + full_text
        live.update(Panel(
            content,
            title="[yellow]⚙ Executing[/yellow]",
            border_style="yellow"
        ))

    with Live(
        Panel("Initializing...", title="[yellow]⚙ Executing[/yellow]", border_style="yellow"),
        refresh_per_second=10, console=console
    ) as live:
        result = run_agent(task, status_callback=on_status, token_callback=on_token, session_id="cli")

    return result

def interactive_loop():
    print_banner()
    console.print("[dim]Commands: /quit  /clear  /voice  /debate <q>  /plan <goal>  /today  /stats[/dim]\n")

    while True:
        try:
            raw = session.prompt("Jarvis> ").strip()
            if not raw:
                continue

            # Built-in commands
            if raw.lower() in ["/quit", "/exit", "exit", "quit"]:
                console.print("[bold red]Session terminated.[/bold red]")
                break

            if raw.lower() == "/clear":
                os.system("clear")
                print_banner()
                continue

            if raw.lower() == "/today":
                from planner import get_todays_tasks
                tasks = get_todays_tasks()
                if tasks:
                    console.print(Panel("\n".join(f"• {t}" for t in tasks),
                                        title="☀️ Today's Tasks", border_style="green"))
                else:
                    console.print("[yellow]No tasks scheduled. Use /plan to create a goal.[/yellow]")
                continue

            if raw.lower() == "/stats":
                from orchestrator import get_routing_report
                console.print(Markdown(get_routing_report()))
                continue

            if raw.lower().startswith("/debate "):
                q = raw[8:].strip()
                console.print("[cyan]⚖️ Starting debate...[/cyan]")
                from debate import run_debate
                result = run_debate(q)
                console.print(Panel(Markdown(result), title="⚖️ Debate Result", border_style="cyan"))
                continue

            if raw.lower().startswith("/plan "):
                goal = raw[6:].strip()
                from planner import create_plan
                console.print("[cyan]📅 Building your plan...[/cyan]")
                plan = create_plan(goal)
                weeks = len(plan.get("milestones", []))
                console.print(Panel(
                    f"**Goal:** {plan.get('goal')}\n"
                    f"**Deadline:** {plan.get('deadline')}\n"
                    f"**Duration:** {weeks} weeks\n\n"
                    f"Use /today to see today's tasks.",
                    title="📅 Plan Created", border_style="green"
                ))
                continue

            if raw.lower() == "/voice":
                console.print("[cyan]🎙️ Starting voice assistant...[/cyan]")
                from voice_assistant import trigger_once
                trigger_once(agent_fn=run_agent)
                continue

            # Regular task
            result = run_task(raw)
            console.print(Panel(
                Markdown(result),
                title="[bold green]✅ Result[/bold green]",
                border_style="green"
            ))
            console.print()

        except KeyboardInterrupt:
            console.print("[yellow]Cancelled.[/yellow]")
        except EOFError:
            break
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

def main():
    parser = argparse.ArgumentParser(description="JARVIS CLI v2")
    parser.add_argument("task",      nargs="?", help="Task to execute")
    parser.add_argument("--voice",   action="store_true", help="Start voice assistant")
    parser.add_argument("--debate",  metavar="Q", help="Multi-model debate")
    parser.add_argument("--plan",    metavar="GOAL", help="Create long-horizon plan")
    parser.add_argument("--morning", action="store_true", help="Morning briefing")
    parser.add_argument("--doctor",  action="store_true", help="Run system health check")
    args = parser.parse_args()

    if args.doctor:
        from doctor import run_doctor
        run_doctor()
        return

    if args.voice:
        from voice_assistant import run_voice_loop
        run_voice_loop(agent_fn=run_agent)
        return

    if args.debate:
        print_banner()
        from debate import run_debate
        result = run_debate(args.debate)
        console.print(Panel(Markdown(result), title="⚖️ Debate", border_style="cyan"))
        return

    if args.plan:
        from planner import create_plan
        plan = create_plan(args.plan)
        console.print(f"[green]Plan created: {len(plan.get('milestones',[]))} weeks[/green]")
        return

    if args.morning:
        from planner import get_morning_briefing
        console.print(Panel(Markdown(get_morning_briefing()),
                            title="☀️ Morning Briefing", border_style="yellow"))
        return

    if args.task:
        print_banner()
        result = run_task(args.task)
        console.print(Panel(Markdown(result), border_style="green"))
        return

    # Default: interactive
    interactive_loop()

if __name__ == "__main__":
    main()
