"""JARVIS CLI — Main interactive REPL loop with rich formatting."""

import asyncio
import os
import readline
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from jarvis.cli_ui.safety import ask_confirm, is_dangerous
from jarvis.cli_ui.streaming import stream_response, stream_tool_result
from jarvis.tools import TOOL_DEFINITIONS, dispatch_tool

_HISTORY_FILE = Path.home() / ".jarvis_cli_history"
_TOOL_NAMES = [t["name"] for t in TOOL_DEFINITIONS]
_KNOWN_SLASH_COMMANDS = {"/help", "/quit", "/exit", "/tools", "/clear", "/voice"}


class InteractiveEngine:
    def __init__(self, console=None):
        self.console = console or Console()
        self.session_history: list[dict] = []
        self.system_prompt = (
            "You are JARVIS, an AI assistant. "
            "Be concise, helpful, and accurate. "
            "Use markdown for formatting when helpful."
        )

    def _show_banner(self) -> None:
        banner_text = Text()
        banner_text.append("🧠 JARVIS v3  —  Interactive Console\n", style="bold cyan")
        banner_text.append("Type your command or ask anything.\n", style="dim")
        banner_text.append("/help for commands  /quit to exit", style="dim")
        self.console.print(
            Panel(
                banner_text,
                border_style="cyan",
                style="on black",
            )
        )

    def _setup_readline(self) -> None:
        try:
            readline.parse_and_bind("tab: complete")
            if _HISTORY_FILE.exists():
                readline.read_history_file(str(_HISTORY_FILE))
        except Exception:
            pass

    def _save_history(self) -> None:
        try:
            _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            readline.write_history_file(str(_HISTORY_FILE))
        except Exception:
            pass

    def run(self) -> None:
        """Main REPL loop."""
        self._setup_readline()
        self._show_banner()

        while True:
            try:
                raw = input("\001\033[1;36m\002JARVIS>\001\033[0m\002 ").strip()
            except (EOFError, KeyboardInterrupt):
                self.console.print("\nGoodbye.")
                break

            if not raw:
                continue

            result = self.process(raw)
            if result == "EXIT":
                break

        self._save_history()

    def process(self, text: str, *, voice_mode: bool = False) -> str:
        """Process a single input. Returns response text.

        When voice_mode=True, minimize output (no banner, just result).
        """
        text = text.strip()
        if not text:
            return ""

        # ── Slash commands ──────────────────────────────────────────
        lower = text.lower()
        if lower in ("/quit", "/exit"):
            if not voice_mode:
                self.console.print("Goodbye.")
            return "EXIT"

        if lower == "/help":
            help_text = (
                "[bold cyan]JARVIS Interactive CLI[/bold cyan]\n\n"
                "[bold]Slash commands:[/bold]\n"
                "  /help     Show this help message\n"
                "  /quit     Exit the REPL\n"
                "  /exit     Same as /quit\n"
                "  /tools    List available tools\n"
                "  /clear    Clear the screen\n"
                "  /voice    Toggle voice mode\n\n"
                "[bold]Shortcuts:[/bold]\n"
                "  $ <cmd>   Execute a shell command\n"
                "  /<cmd>    Execute a shell command (if not a slash command)\n\n"
                "Anything else is sent to the AI for a response."
            )
            self.console.print(Panel(help_text, border_style="cyan"))
            return help_text

        if lower == "/tools":
            tools_text = "\n".join(f"  • {name}" for name in _TOOL_NAMES)
            self.console.print(
                Panel(
                    tools_text,
                    title="[bold cyan]Available Tools[/bold cyan]",
                    border_style="cyan",
                )
            )
            return tools_text

        if lower == "/clear":
            self.console.clear()
            if not voice_mode:
                self._show_banner()
            return ""

        if lower == "/voice":
            msg = "Voice mode toggled. (TTS integration not yet implemented.)"
            self.console.print(f"[yellow]{msg}[/yellow]")
            return msg

        # ── Shell passthrough ───────────────────────────────────────
        is_shell = False
        shell_cmd = ""
        if text.startswith("$"):
            is_shell = True
            shell_cmd = text[1:].strip()
        elif text.startswith("/") and lower not in _KNOWN_SLASH_COMMANDS:
            is_shell = True
            shell_cmd = text[1:].strip()

        if is_shell and shell_cmd:
            dangerous, reason = is_dangerous(shell_cmd)
            if dangerous:
                self.console.print(f"[yellow]⚠ {reason}[/yellow]")
                if not ask_confirm(self.console, "Execute anyway?"):
                    self.console.print("[dim]Cancelled.[/dim]")
                    return ""
            try:
                result = subprocess.run(
                    shell_cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                out = result.stdout.strip() or result.stderr.strip() or "(no output)"
                self.console.print(
                    Panel(
                        Syntax(out, "bash", theme="monokai"),
                        title=f"[bold green]$ {shell_cmd[:40]}[/bold green]",
                        border_style="green",
                    )
                )
                return out
            except subprocess.TimeoutExpired:
                self.console.print(
                    Panel("[red]Command timed out after 30s[/red]", border_style="red")
                )
                return "[ERROR] Command timed out"
            except Exception as exc:
                self.console.print(
                    Panel(f"[red]{exc}[/red]", title="[bold red]Shell Error[/bold red]", border_style="red")
                )
                return f"[ERROR] {exc}"

        # ── Tool dispatching ────────────────────────────────────────
        matched_tool = None
        # Exact match first
        if text in _TOOL_NAMES:
            matched_tool = text
        else:
            # Keyword match: tool name appears as a word in the input
            lower_text = text.lower()
            for name in _TOOL_NAMES:
                if name.lower() in lower_text:
                    matched_tool = name
                    break

        if matched_tool:
            if not voice_mode:
                self.console.print(f"[dim][tool] {matched_tool}()[/dim]")

            # Run dispatch in a thread to avoid blocking the event loop
            # (though process() is sync, this keeps it responsive if we add async later)
            try:
                result = dispatch_tool(matched_tool, {})
            except Exception as exc:
                result = f"[ERROR] {exc}"

            stream_tool_result(matched_tool, result, self.console)
            return result

        # ── Chat / AI fallback ──────────────────────────────────────
        messages = [
            {"role": "system", "content": self.system_prompt},
            *self.session_history,
            {"role": "user", "content": text},
        ]

        async def _chat() -> str:
            full = ""
            try:
                async for chunk in stream_response(
                    messages, self.console, model="jarvis-custom-v2", max_tokens=300
                ):
                    full += chunk
            except RuntimeError:
                full = "[ERROR] Failed to reach Ollama. Is it running?"
                if voice_mode:
                    pass  # already printed by stream_response
                else:
                    self.console.print(f"[red]{full}[/red]")
            return full

        try:
            response = asyncio.run(_chat())
        except Exception as exc:
            response = f"[ERROR] {exc}"
            self.console.print(
                Panel(response, title="[bold red]Error[/bold red]", border_style="red")
            )

        # Update history (keep last ~8 exchanges to stay within token budget)
        self.session_history.append({"role": "user", "content": text})
        self.session_history.append({"role": "assistant", "content": response})
        if len(self.session_history) > 16:
            self.session_history = self.session_history[-16:]

        return response
