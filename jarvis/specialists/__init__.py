"""Specialist agent prompts loaded from pro-workflow patterns."""

from pathlib import Path
from typing import Dict


def load_specialist(name: str) -> str:
    """Load a specialist prompt by name."""
    here = Path(__file__).parent
    path = here / f"{name}.md"
    if path.exists():
        return path.read_text()
    raise FileNotFoundError(f"Specialist '{name}' not found at {path}")


def list_specialists() -> Dict[str, str]:
    """Return mapping of name -> description for all available specialists."""
    here = Path(__file__).parent
    specs = {}
    for f in here.glob("*.md"):
        first_line = f.read_text().splitlines()[0] if f.stat().st_size else ""
        specs[f.stem] = first_line.lstrip("# ").strip()
    return specs
