"""JARVIS Interactive CLI — Claude Code / Gemini CLI style terminal REPL."""

from jarvis.cli_ui.engine import InteractiveEngine
from jarvis.cli_ui.safety import ask_confirm, is_dangerous
from jarvis.cli_ui.streaming import stream_response, stream_tool_result


def run_interactive() -> None:
    """Entry point for `jarvis` with no args."""
    engine = InteractiveEngine()
    engine.run()


def process(text: str, console=None, voice_mode: bool = False) -> str:
    """Process a single input. Returns response text."""
    engine = InteractiveEngine(console=console)
    return engine.process(text, voice_mode=voice_mode)
