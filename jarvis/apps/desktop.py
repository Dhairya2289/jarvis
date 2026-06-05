"""JARVIS Desktop App Discovery & Control

Discovers all installed apps via freedesktop .desktop files
and exposes launch/focus/query operations.
"""
from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from jarvis.config import LOG_FILE

_log = logging.getLogger(__name__)

_DESKTOP_DIRS: Final[list[Path]] = [
    Path("/usr/share/applications"),
    Path("/usr/local/share/applications"),
    Path.home() / ".local" / "share" / "applications",
]


@dataclass
class DesktopApp:
    name: str
    exec: str
    icon: str = ""
    categories: list[str] = field(default_factory=list)
    comment: str = ""
    keywords: list[str] = field(default_factory=list)
    terminal: bool = False
    source_file: Path | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "exec": self.exec,
            "icon": self.icon,
            "categories": self.categories,
            "comment": self.comment,
            "keywords": self.keywords,
            "terminal": self.terminal,
            "source_file": str(self.source_file) if self.source_file else None,
        }


def _parse_desktop_file(path: Path) -> DesktopApp | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    if not text.startswith("[Desktop Entry]"):
        return None
    data: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            data[k] = v.strip()
    if data.get("Type") != "Application":
        return None
    if data.get("NoDisplay", "false").lower() == "true":
        return None
    if data.get("Hidden", "false").lower() == "true":
        return None

    exec_str = data.get("Exec", "")
    # Strip field codes (%f, %F, %u, %U, etc.)
    exec_str = " ".join(p for p in exec_str.split() if not p.startswith("%"))

    categories = [c.strip() for c in data.get("Categories", "").split(";") if c.strip()]
    keywords = [k.strip() for k in data.get("Keywords", "").split(";") if k.strip()]

    return DesktopApp(
        name=data.get("Name", path.stem),
        exec=exec_str,
        icon=data.get("Icon", ""),
        categories=categories,
        comment=data.get("Comment", ""),
        keywords=keywords,
        terminal=data.get("Terminal", "false").lower() == "true",
        source_file=path,
    )


def list_apps() -> list[DesktopApp]:
    """Return all discoverable applications, sorted by name."""
    apps: list[DesktopApp] = []
    seen = set()
    for d in _DESKTOP_DIRS:
        if not d.exists():
            continue
        for path in d.glob("*.desktop"):
            app = _parse_desktop_file(path)
            if app and app.exec and app.name not in seen:
                seen.add(app.name)
                apps.append(app)
    apps.sort(key=lambda a: a.name.lower())
    _log.info("Discovered %d apps from %d dirs", len(apps), len(_DESKTOP_DIRS))
    return apps


def search_apps(query: str) -> list[DesktopApp]:
    """Search by name, comment, category, or keyword."""
    q = query.lower()
    results = []
    for app in list_apps():
        if (
            q in app.name.lower()
            or q in app.comment.lower()
            or any(q in c.lower() for c in app.categories)
            or any(q in k.lower() for k in app.keywords)
        ):
            results.append(app)
    return results


def launch_app(name: str) -> str:
    """Launch an app by its display name."""
    for app in list_apps():
        if app.name.lower() == name.lower():
            try:
                if app.terminal:
                    subprocess.Popen(["kitty", "--", "sh", "-c", app.exec])
                else:
                    subprocess.Popen(app.exec.split())
                time.sleep(0.5)
                _log.info("Launched: %s (%s)", app.name, app.exec)
                return f"Launched: {app.name}"
            except Exception as exc:
                _log.error("Failed to launch %s: %s", app.name, exc)
                return f"[ERROR] Failed to launch {app.name}: {exc}"
    return f"App '{name}' not found."


def focus_app(name: str) -> str:
    """Focus an existing window via hyprctl dispatch."""
    try:
        result = subprocess.run(
            ["hyprctl", "dispatch", "focuswindow", f"title:^{name}$"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if "ok" in result.stdout.lower() or result.returncode == 0:
            return f"Focused: {name}"
    except Exception:
        pass
    # Fallback: try class match
    try:
        result = subprocess.run(
            ["hyprctl", "dispatch", "focuswindow", f"class:^{name}$"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if "ok" in result.stdout.lower() or result.returncode == 0:
            return f"Focused: {name}"
    except Exception as exc:
        return f"[ERROR] hyprctl failed: {exc}"
    return f"Window '{name}' not found."


def list_apps_markdown() -> str:
    """Return a markdown list of all apps."""
    apps = list_apps()
    lines = [f"# Desktop Apps ({len(apps)} total)", ""]
    for app in apps:
        terminal_icon = "🖥️" if app.terminal else ""
        lines.append(f"- **{app.name}** {terminal_icon}\n  `{app.exec}`")
        if app.comment:
            lines.append(f"  {app.comment}")
    return "\n".join(lines)


def _mirror_to_obsidian(action: str, detail: str) -> None:
    try:
        from jarvis.obsidian_brain import ObsidianBrain
        ObsidianBrain().append_daily(f"[DESKTOP] {action}: {detail}")
    except Exception:
        pass


__all__ = [
    "DesktopApp",
    "list_apps",
    "search_apps",
    "launch_app",
    "focus_app",
    "list_apps_markdown",
]
