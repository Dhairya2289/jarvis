"""JARVIS CLI — Dangerous shell command detection and confirmation prompts."""

from rich.console import Console
from rich.prompt import Confirm

DANGEROUS_COMMANDS = {
    "rm", "dd", "mkfs", "fdisk", "mkfs.ext", "chmod", "chown", "wget", "curl"
}
SAFE_COMMANDS = {
    "ls", "cat", "echo", "pwd", "grep", "find", "head", "tail", "wc",
    "mkdir", "touch", "cd", "df", "du", "ps", "top", "htop", "glances",
    "neofetch", "git", "python3", "pip", "pip3"
}


def is_dangerous(cmd: str) -> tuple[bool, str]:
    """Return (is_dangerous, reason). Reason is empty if safe."""
    stripped = cmd.strip()
    if stripped.startswith("$"):
        stripped = stripped[1:].strip()
    if stripped.startswith("/") and not stripped.startswith("//"):
        stripped = stripped[1:].strip()

    tokens = stripped.split()
    if not tokens:
        return False, ""

    first = tokens[0]

    if first in SAFE_COMMANDS:
        return False, ""

    if first in DANGEROUS_COMMANDS:
        return True, f"Command '{first}' is flagged as potentially dangerous."

    for token in tokens:
        if token in DANGEROUS_COMMANDS:
            return True, f"Command contains dangerous token '{token}'."

    return False, ""


def ask_confirm(console: Console, message: str) -> bool:
    """Use rich.prompt to ask Y/n. Return True if confirmed."""
    try:
        return Confirm.ask(message, console=console, default=False)
    except Exception:
        # Fallback if rich prompt fails (e.g. piped input)
        raw = input(f"{message} [y/N]: ").strip().lower()
        return raw in ("y", "yes")
