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
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
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
    parser.add_argument("--dashboard", action="store_true", help="Launch the JARVIS web dashboard")
    parser.add_argument("--vision", action="store_true", help="Capture screen and ask vision model")
    parser.add_argument("--workflow", nargs="*", help="Workflow subcommand")
    parser.add_argument("--loop", action="store_true", help="Start the unified JARVIS agent loop")
    parser.add_argument("--search", metavar="QUERY", help="Search across all sources via universal search")
    parser.add_argument("--index-files", nargs="?", const=str(Path.home()), metavar="PATH", help="Index files for search (default: home)")
    parser.add_argument("--ingest-pdf", metavar="PATH", help="Ingest a PDF document")
    parser.add_argument("--organize-downloads", action="store_true", help="Organize downloads folder")
    parser.add_argument("--rss-digest", action="store_true", help="Generate RSS feed digest")
    parser.add_argument("--feeds", metavar="URLS", help="Comma-separated RSS feed URLs (use with --rss-digest)")
    parser.add_argument("--add-todo", metavar="MESSAGE", help="Add a todo item")
    parser.add_argument("--list-todos", nargs="?", const="open", metavar="STATUS", choices=["open", "done"], help="List todos (open or done)")
    parser.add_argument("--snapshot", action="store_true", help="Take a workspace memory snapshot")
    parser.add_argument("--restore", metavar="FILE", help="Restore workspace from snapshot file")
    parser.add_argument("--launch", metavar="QUERY", help="Smart application launcher")
    parser.add_argument("--clipboard-history", nargs="?", const="10", metavar="N", help="Get clipboard history (last N items)")
    parser.add_argument("--notifications", nargs="?", const="10", metavar="N", help="Get recent notifications (last N)")
    parser.add_argument("--archive-screenshots", action="store_true", help="Archive old screenshots")
    parser.add_argument("--window-timeline", nargs="?", const="24", metavar="HOURS", help="Get window activity timeline")
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

    if args.dashboard:
        _launch_dashboard()
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

    # ── 14 new feature handlers ───────────────────────────────────────

    if args.search:
        try:
            from jarvis.universal_search import universal_search
            result = _run_sync(universal_search(args.search))
            if RICH_AVAILABLE:
                console.print(result)  # type: ignore
            else:
                print(result)
        except Exception as e:
            print(f"Search error: {e}")
        return

    if args.index_files:
        try:
            from jarvis.file_search_index import FileSearchIndex
            idx = FileSearchIndex()
            idx.scan(Path(args.index_files))
            msg = f"Indexed files in: {args.index_files}"
            if RICH_AVAILABLE:
                console.print(f"[green]✔[/green] {msg}")  # type: ignore
            else:
                print(f"OK: {msg}")
        except Exception as e:
            print(f"Index error: {e}")
        return

    if args.ingest_pdf:
        try:
            from jarvis.pdf_ingestion import PDFIngestion
            PDFIngestion().ingest(Path(args.ingest_pdf))
            msg = f"Ingested: {args.ingest_pdf}"
            if RICH_AVAILABLE:
                console.print(f"[green]✔[/green] {msg}")  # type: ignore
            else:
                print(f"OK: {msg}")
        except Exception as e:
            print(f"PDF ingestion error: {e}")
        return

    if args.organize_downloads:
        try:
            from jarvis.download_organizer import DownloadOrganizer
            count = DownloadOrganizer().organize(dry_run=False)
            msg = f"Organized {count} files in Downloads"
            if RICH_AVAILABLE:
                console.print(f"[green]✔[/green] {msg}")  # type: ignore
            else:
                print(f"OK: {msg}")
        except Exception as e:
            print(f"Organize error: {e}")
        return

    if args.rss_digest:
        try:
            from jarvis.rss_reader import RSSReader
            feed_urls = args.feeds.split(",") if args.feeds else ["https://hnrss.org/frontpage"]
            reader = RSSReader(feed_urls)
            digest = reader.get_digest(datetime.now() - timedelta(days=1))
            if RICH_AVAILABLE:
                console.print(digest)  # type: ignore
            else:
                print(digest)
        except Exception as e:
            print(f"RSS digest error: {e}")
        return

    if args.add_todo:
        try:
            from jarvis.smart_todo import SmartTodo
            vault = Path.home() / "obsidian" / "JARVIS"
            todo = SmartTodo(vault)
            todo.parse_message(args.add_todo)
            todo.add_items()
            if RICH_AVAILABLE:
                console.print("[green]✔[/green] Todo added")  # type: ignore
            else:
                print("OK: Todo added")
        except Exception as e:
            print(f"Todo error: {e}")
        return

    if args.list_todos is not None:
        try:
            from jarvis.smart_todo import SmartTodo
            vault = Path.home() / "obsidian" / "JARVIS"
            todo = SmartTodo(vault)
            items = todo.list_items(args.list_todos)
            if RICH_AVAILABLE:
                console.print(f"[bold]Todos ({args.list_todos}):[/bold]")  # type: ignore
                for item in items:
                    console.print(f"  • {item}")  # type: ignore
            else:
                print(f"Todos ({args.list_todos}):")
                for item in items:
                    print(f"  • {item}")
        except Exception as e:
            print(f"List todos error: {e}")
        return

    if args.snapshot:
        try:
            from jarvis.desktop.workspace_memory import WorkspaceMemory
            snap = WorkspaceMemory().snapshot()
            output = json.dumps(snap, indent=2, default=str)
            if RICH_AVAILABLE:
                console.print(output)  # type: ignore
            else:
                print(output)
        except Exception as e:
            print(f"Snapshot error: {e}")
        return

    if args.restore:
        try:
            from jarvis.desktop.workspace_memory import WorkspaceMemory
            data = json.loads(open(args.restore).read())
            WorkspaceMemory().restore(data)
            if RICH_AVAILABLE:
                console.print(f"[green]✔[/green] Restored from {args.restore}")  # type: ignore
            else:
                print(f"OK: Restored from {args.restore}")
        except Exception as e:
            print(f"Restore error: {e}")
        return

    if args.launch:
        try:
            from jarvis.desktop.smart_launcher import smart_launch
            smart_launch(args.launch)
        except Exception as e:
            print(f"Launch error: {e}")
        return

    if args.clipboard_history is not None:
        try:
            from jarvis.desktop.clipboard_history import ClipboardHistory
            n = int(args.clipboard_history)
            items = ClipboardHistory().get_recent(n)
            if RICH_AVAILABLE:
                console.print(f"[bold]Clipboard history (last {n}):[/bold]")  # type: ignore
                for item in items:
                    console.print(f"  {item}")  # type: ignore
            else:
                print(f"Clipboard history (last {n}):")
                for item in items:
                    print(f"  {item}")
        except Exception as e:
            print(f"Clipboard error: {e}")
        return

    if args.notifications is not None:
        try:
            from jarvis.desktop.notification_triage import NotificationTriage
            n = int(args.notifications)
            items = NotificationTriage().recent(n)
            if RICH_AVAILABLE:
                console.print(f"[bold]Recent notifications ({n}):[/bold]")  # type: ignore
                for item in items:
                    console.print(f"  {item}")  # type: ignore
            else:
                print(f"Recent notifications ({n}):")
                for item in items:
                    print(f"  {item}")
        except Exception as e:
            print(f"Notifications error: {e}")
        return

    if args.archive_screenshots:
        try:
            from jarvis.desktop.screenshot_manager import ScreenshotManager
            count = ScreenshotManager().archive()
            msg = f"Archived {count} screenshots"
            if RICH_AVAILABLE:
                console.print(f"[green]✔[/green] {msg}")  # type: ignore
            else:
                print(f"OK: {msg}")
        except Exception as e:
            print(f"Screenshot archive error: {e}")
        return

    if args.window_timeline is not None:
        try:
            from jarvis.desktop.window_logger import WindowLogger
            hours = int(args.window_timeline)
            timeline = WindowLogger().get_timeline(since=hours * 3600)
            if RICH_AVAILABLE:
                console.print(f"[bold]Window timeline (last {hours}h):[/bold]")  # type: ignore
                console.print(timeline)  # type: ignore
            else:
                print(f"Window timeline (last {hours}h):")
                print(timeline)
        except Exception as e:
            print(f"Window timeline error: {e}")
        return

    # ── end new feature handlers ──────────────────────────────────────

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


def _launch_dashboard() -> None:
    """Start the FastAPI server and open the dashboard in a browser/webview."""
    import threading
    import time
    import urllib.request
    from jarvis.gui_server import app as gui_app
    import uvicorn

    def _run_server():
        uvicorn.run(gui_app, host="127.0.0.1", port=5050, log_level="warning")

    server_thread = threading.Thread(target=_run_server, daemon=True)
    server_thread.start()

    # Wait for server to be ready
    for _ in range(20):
        try:
            urllib.request.urlopen("http://127.0.0.1:5050/api/health", timeout=1)
            break
        except Exception:
            time.sleep(0.5)

    # Try webview first, fall back to browser
    try:
        from jarvis.launch_gui import launch_gui
        launch_gui()
    except SystemExit:
        # pywebview not installed — fallback to browser
        import webbrowser
        webbrowser.open("http://127.0.0.1:5050/static/dashboard.html")
        if RICH_AVAILABLE:
            console.print("[bold cyan]JARVIS Dashboard running at http://127.0.0.1:5050[/bold cyan]")
            console.print("[dim]Press Ctrl+C to stop[/dim]")
        else:
            print("JARVIS Dashboard running at http://127.0.0.1:5050")
            print("Press Ctrl+C to stop")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
