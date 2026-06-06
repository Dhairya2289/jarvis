"""JARVIS Desktop Analytics — screen-time insights and daily reports."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

LOG_PATH = Path.home() / ".jarvis" / "desktop_window_log.jsonl"


def parse_logs(hours: int = 24) -> list[dict]:
    """Parse recent window logs."""
    logs = []
    cutoff = datetime.now() - timedelta(hours=hours)
    if not LOG_PATH.exists():
        return logs
    with open(LOG_PATH) as f:
        for line in f:
            try:
                entry = json.loads(line)
                ts = datetime.fromisoformat(entry.get("timestamp", "1970-01-01"))
                if ts >= cutoff:
                    logs.append(entry)
            except Exception:
                continue
    return logs


def generate_daily_report(hours: int = 24) -> str:
    """Analyze window logs and return a markdown report."""
    logs = parse_logs(hours)
    if not logs:
        return "📊 No window activity tracked in the last 24 hours."

    # Sort chronologically so we can compute durations between events
    logs.sort(key=lambda e: datetime.fromisoformat(e.get("timestamp", "1970-01-01T00:00:00")))

    app_times = defaultdict(float)
    app_windows = defaultdict(set)
    hourly_activity = defaultdict(int)

    now = datetime.now()

    for i, entry in enumerate(logs):
        cls = entry.get("class_name", "Unknown")
        title = entry.get("title", "")
        ts = datetime.fromisoformat(entry.get("timestamp", "1970-01-01T00:00:00"))

        # Duration = time until next event, or until now for the last event.
        if i + 1 < len(logs):
            next_ts = datetime.fromisoformat(
                logs[i + 1].get("timestamp", "1970-01-01T00:00:00")
            )
        else:
            next_ts = now

        duration = (next_ts - ts).total_seconds()
        # Cap duration at 1 hour to avoid inflated numbers from long idle gaps
        duration = min(duration, 3600.0)

        app_times[cls] += duration
        app_windows[cls].add(title)
        hourly_activity[ts.hour] += 1

    total_seconds = sum(app_times.values())
    top_apps = Counter(app_times).most_common(5)

    lines = [f"📊 Today's screen time ({total_seconds / 3600:.1f}h total):\n"]
    for app, secs in top_apps:
        pct = secs / total_seconds * 100 if total_seconds else 0
        lines.append(f"  • {app}: {secs / 60:.0f}min ({pct:.0f}%)")

    # Peak hours
    if hourly_activity:
        peak_hour = max(hourly_activity, key=hourly_activity.get)
        lines.append(
            f"\n🔥 Peak activity: {peak_hour}:00-{peak_hour + 1}:00 "
            f"({hourly_activity[peak_hour]} events)"
        )

    # Context tags (simple heuristic)
    context = _infer_context(top_apps)
    lines.append(f"\n📝 Context: {context}")

    return "\n".join(lines)


def _infer_context(top_apps: list[tuple[str, float]]) -> str:
    """Infer work context from app usage."""
    dev_apps = {
        "code", "vscode", "nvim", "terminal", "foot", "alacritty", "kitty",
        "wezterm", "code-oss", "vscodium", "cursor", "zed", "sublime_text",
    }
    comm_apps = {
        "discord", "telegram", "slack", "mail", "thunderbird", "element",
        "signal", "telegramdesktop", "web.whatsapp", "whatsapp", "teams", "zoom",
    }
    media_apps = {
        "firefox", "chromium", "brave", "chrome", "edge", "opera", "mpv",
        "vlc", "spotify", "youtube", "netflix", "obs",
    }

    apps = {a.lower() for a, _ in top_apps}
    if apps & dev_apps and not apps & media_apps:
        return "Deep work / coding session"
    if apps & comm_apps:
        return "Communication / collaboration"
    if apps & media_apps:
        return "Browsing / media consumption"
    return "General productivity"
