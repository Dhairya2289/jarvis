from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import threading
import time
from datetime import date, datetime
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

import requests
import anthropic
from bs4 import BeautifulSoup
from jarvis_v3.config import (
    MONITOR_URLS, MONITOR_INTERVAL, WORLD_CACHE,
    TELEGRAM_TOKEN, ALLOWED_USER_IDS, FCC_BASE_URL, FCC_AUTH_TOKEN, MODELS
)

_LOG = logging.getLogger(__name__)

client = anthropic.Anthropic(base_url=FCC_BASE_URL, api_key=FCC_AUTH_TOKEN)

# ── Default sites to watch (merged with user config) ──────
DEFAULT_MONITORS = [
    # Add IISER/CUET/NTA if user studying for exams
    "https://ntaonline.in/",
    "https://github.com/trending",
]
ALL_MONITORS = list(set(DEFAULT_MONITORS + [u for u in MONITOR_URLS if u.strip()]))

# ── Cache ─────────────────────────────────────────────────

def _load_cache() -> Dict[str, Any]:
    """Load the world model cache from disk.

    Returns:
        Dictionary representing the cache.
    """
    try:
        return json.loads(Path(WORLD_CACHE).read_text())
    except Exception as e:
        _LOG.debug("Failed to load cache: %s", e)
        return {}

def _save_cache(cache: Dict[str, Any]) -> None:
    """Save the world model cache to disk.

    Args:
        cache: Dictionary to save.
    """
    try:
        Path(WORLD_CACHE).write_text(json.dumps(cache, indent=2))
        _LOG.debug("Saved world cache")
    except Exception as e:
        _LOG.error("Failed to save cache: %s", e)

def _page_hash(url: str) -> Tuple[str, str]:
    """Fetch page and return (content_hash, clean_text).

    Args:
        url: The URL to fetch.

    Returns:
        Tuple of (MD5 hash of cleaned text, cleaned text string).
    """
    try:
        r = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101"},
            timeout=15
        )
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)[:3000]
        return hashlib.md5(text.encode()).hexdigest(), text
    except Exception as e:
        _LOG.debug("Error fetching %s: %s", url, e)
        return "", f"[ERROR fetching {url}: {e}]"

# ── Change Analysis ───────────────────────────────────────

def _is_relevant_change(url: str, old_text: str, new_text: str) -> Tuple[bool, str]:
    """Ask AI if the change is worth notifying about.

    Args:
        url: The URL that changed.
        old_text: The previous cleaned text.
        new_text: The new cleaned text.

    Returns:
        Tuple of (boolean indicating relevance, summary string if relevant).
    """
    prompt = (
        f"A webpage changed: {url}\n\n"
        f"Old content snippet: {old_text[:600]}\n"
        f"New content snippet: {new_text[:600]}\n\n"
        f"Is this a SIGNIFICANT change (new announcement, exam date, important update)?\n"
        f"Respond: NOTIFY: <one sentence summary> OR IGNORE"
    )
    try:
        r = client.messages.create(
            model=MODELS["speed"][1], max_tokens=80,
            messages=[{"role": "user", "content": prompt}]
        )
        result = r.content[0].text.strip()
        if result.startswith("NOTIFY:"):
            return True, result[7:].strip()
        return False, ""
    except Exception as e:
        _LOG.debug("Error in relevance check for %s: %s", url, e)
        return False, ""

# ── Telegram notification ─────────────────────────────────

def _telegram_push(message: str) -> None:
    """Send a message via Telegram bot.

    Args:
        message: The message to send.
    """
    if not TELEGRAM_TOKEN or not ALLOWED_USER_IDS:
        _LOG.debug("[WORLD] No Telegram configured. Alert: %s", message)
        return
    for uid in ALLOWED_USER_IDS:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": uid, "text": message, "parse_mode": "Markdown"},
                timeout=10
            )
        except Exception as e:
            _LOG.debug("Failed to send Telegram message to %s: %s", uid, e)

# ── Site monitoring loop ──────────────────────────────────

def _monitor_cycle() -> List[Tuple[str, str]]:
    """Run one cycle of site monitoring.

    Returns:
        List of tuples (url, summary) for relevant changes.
    """
    cache = _load_cache()
    changed: List[Tuple[str, str]] = []

    for url in ALL_MONITORS:
        h, text = _page_hash(url)
        if not h:
            continue

        prev = cache.get(url, {})
        if prev.get("hash") == h:
            continue   # No change

        if prev.get("hash"):   # First time = no notification
            relevant, summary = _is_relevant_change(
                url, prev.get("text", ""), text
            )
            if relevant:
                changed.append((url, summary))

        cache[url] = {"hash": h, "text": text[:1000], "last_checked": time.time()}

    _save_cache(cache)
    return changed

# ── Daily tasks push ──────────────────────────────────────

def _morning_briefing_push() -> None:
    """Push morning briefing at configured time."""
    try:
        from planner import get_morning_briefing
        briefing = get_morning_briefing()
        if briefing:
            _telegram_push(f"☀️ *Good morning!*\n\n{briefing}")
    except Exception as e:
        _LOG.error("Morning briefing error: %s", e)

# ── System health check ───────────────────────────────────

def _check_system_health() -> List[str]:
    """Check system health and return a list of alert strings.

    Returns:
        List of health alert messages.
    """
    alerts: List[str] = []
    try:
        # Disk usage
        r = subprocess.run(["df", "-h", "/"], capture_output=True, text=True)
        for line in r.stdout.splitlines()[1:]:
            parts = line.split()
            if parts and parts[4].endswith("%"):
                pct = int(parts[4].rstrip("%"))
                if pct > 88:
                    alerts.append(f"⚠️ Disk {parts[4]} full on {parts[5]}")

        # High memory
        r = subprocess.run(["free", "-m"], capture_output=True, text=True)
        for line in r.stdout.splitlines():
            if line.startswith("Mem:"):
                parts = line.split()
                total, used = int(parts[1]), int(parts[2])
                if used / total > 0.90:
                    alerts.append(f"⚠️ RAM usage {used}/{total}MB (>90%)")
    except Exception as e:
        _LOG.debug("Error checking system health: %s", e)
    return alerts

# ── Main background thread ────────────────────────────────

_running = False

def start_background(interval: Optional[int] = None) -> None:
    """Start the world model as a background daemon thread.

    Args:
        interval: Optional interval in seconds (defaults to MONITOR_INTERVAL).
    """
    global _running
    if _running:
        return
    _running = True
    interval = interval or MONITOR_INTERVAL

    last_morning = None

    def _loop() -> None:
        while _running:
            now = datetime.now()

            # Morning briefing at 7:30 AM (once per day)
            if now.hour == 7 and now.minute >= 30:
                if last_morning != date.today():
                    # Use a mutable container to update the closure variable
                    nonlocal_last_morning = [last_morning]
                    if nonlocal_last_morning[0] != date.today():
                        nonlocal_last_morning[0] = date.today()
                        threading.Thread(target=_morning_briefing_push, daemon=True).start()
                    last_morning = nonlocal_last_morning[0]

            # Site monitoring
            changes = _monitor_cycle()
            for url, summary in changes:
                msg = f"🌐 *World Update*\n{url}\n\n{summary}"
                _telegram_push(msg)
                # Also desktop notification
                subprocess.Popen(
                    ["notify-send", "-u", "normal", "🌐 World Update", summary[:200]],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )

            # System health
            health_alerts = _check_system_health()
            for alert in health_alerts:
                _telegram_push(f"🖥️ *System Health*\n{alert}")

            time.sleep(interval)

    t = threading.Thread(target=_loop, daemon=True, name="JarvisWorldModel")
    t.start()
    _LOG.info("[WORLD] Background monitoring started (interval: %ds).", interval)

def stop_background() -> None:
    """Stop the world model background thread."""
    global _running
    _running = False
    _LOG.info("[WORLD] Background monitoring stopped.")

# Define public API
__all__: List[str] = [
    "start_background",
    "stop_background",
]