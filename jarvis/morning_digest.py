"""Morning news digest — RSS + system health summary."""
from __future__ import annotations

from datetime import datetime

from jarvis.rss_reader import get_unread_items
from jarvis.desktop.screenshot_manager import get_system_health


async def generate_morning_digest() -> str:
    """Fetch RSS, summarize, return markdown digest."""
    try:
        news = get_unread_items(limit=20)
        headlines = [n["title"] for n in news[:10]]
    except Exception:
        headlines = []

    try:
        health = get_system_health()
    except Exception:
        health = "System OK"

    digest = "🌅 Good morning!\n\n"
    digest += "📰 Top headlines:\n"
    for h in headlines[:5]:
        digest += f"  • {h}\n"
    digest += f"\n{health}\n"
    return digest
