"""JARVIS CLI — Rich streaming helpers for Ollama SSE."""

import json

import httpx
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel

OLLAMA_URL = "http://localhost:11434/api/chat"


async def stream_response(
    messages: list,
    console: Console,
    *,
    model: str = "jarvis-custom-v2",
    max_tokens: int = 500,
):
    """Stream a chat completion from Ollama with live markdown rendering.

    Uses httpx.AsyncClient streaming to localhost:11434/api/chat.
    Yields each chunk as it's received.
    Renders live with rich.live.Live showing a growing Panel.
    """
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {"num_predict": max_tokens},
    }

    accumulated = ""
    panel = Panel(
        Markdown(accumulated),
        title="[bold cyan]JARVIS[/bold cyan]",
        border_style="cyan",
    )

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", OLLAMA_URL, json=payload) as resp:
                resp.raise_for_status()
                with Live(panel, refresh_per_second=12, console=console, transient=False) as live:
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        if data.get("done"):
                            break

                        chunk = data.get("message", {}).get("content", "")
                        if not chunk:
                            continue

                        accumulated += chunk
                        yield chunk

                        live.update(
                            Panel(
                                Markdown(accumulated),
                                title="[bold cyan]JARVIS[/bold cyan]",
                                border_style="cyan",
                            )
                        )
    except httpx.ConnectError as exc:
        console.print(
            Panel(
                f"[red]Could not connect to Ollama at {OLLAMA_URL}.\n"
                f"Make sure Ollama is running.[/red]",
                title="[bold red]Connection Error[/bold red]",
                border_style="red",
            )
        )
        raise RuntimeError(f"Ollama connection failed: {exc}") from exc
    except httpx.HTTPStatusError as exc:
        console.print(
            Panel(
                f"[red]Ollama returned an error:\n{exc.response.text}[/red]",
                title="[bold red]HTTP Error[/bold red]",
                border_style="red",
            )
        )
        raise RuntimeError(f"Ollama HTTP error: {exc}") from exc


def stream_tool_result(tool_name: str, result: str, console: Console) -> None:
    """Show tool result in a formatted panel."""
    is_error = result.startswith("[ERROR]") or result.startswith("[BLOCKED]")
    border = "red" if is_error else "cyan"
    title = f"[bold {border}][tool] {tool_name}[/bold {border}]"
    console.print(Panel(result, title=title, border_style=border))
