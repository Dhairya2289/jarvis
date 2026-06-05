"""JARVIS Browser Agent v2 — Playwright with smart extraction"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)


def run_browser_task(action: str, params: dict[str, Any]) -> str:
    """Run a browser automation sequence.

    Args:
        action: Reserved for future dispatch; ignored currently.
        params: Must contain ``sequence``, a list of step dicts.
            Each step has ``cmd`` in
            ``{"goto","click","type","wait","content","screenshot"}``,
            plus ``val`` and ``selector`` as needed.

    Returns:
        Joined result lines from each step.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return (
            "[ERROR] playwright not installed.  Run:\n"
            "  pip install playwright && playwright install chromium"
        )

    scr_dir = Path.home() / "Pictures" / "Jarvis"
    scr_dir.mkdir(parents=True, exist_ok=True)

    results: list[str] = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36"
                ),
                viewport={"width": 1280, "height": 800},
            )
            page = ctx.new_page()

            for step in params.get("sequence", []):
                cmd = step.get("cmd")
                val = step.get("val", "")
                selector = step.get("selector", "")

                if cmd == "goto":
                    page.goto(
                        val,
                        wait_until="domcontentloaded",
                        timeout=15000,
                    )
                    results.append(f"Navigated to {val}")

                elif cmd == "click":
                    page.click(selector, timeout=5000)
                    results.append(f"Clicked {selector}")

                elif cmd == "type":
                    page.fill(selector, val)
                    results.append(f"Typed into {selector}")

                elif cmd == "wait":
                    page.wait_for_timeout(int(float(val) * 1000))
                    results.append(f"Waited {val}s")

                elif cmd == "content":
                    html = page.content()
                    try:
                        import trafilatura
                        text = trafilatura.extract(
                            html, include_tables=True
                        ) or ""
                    except ImportError:
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(html, "html.parser")
                        for t in soup(["script", "style", "nav", "footer"]):
                            t.decompose()
                        text = soup.get_text(separator="\n", strip=True)
                    results.append(text[:5000])

                elif cmd == "screenshot":
                    fname = val or f"browser_{int(time.time())}.png"
                    path = scr_dir / fname
                    page.screenshot(
                        path=str(path), full_page=False
                    )
                    results.append(str(path))

                else:
                    results.append(f"[WARN] Unknown browser cmd: {cmd}")

            browser.close()
            return "\n".join(results) if results else "(No output)"

    except Exception as exc:
        _log.error("Browser task failed: %s", exc, exc_info=True)
        return f"[BROWSER ERROR] {exc}"


__all__ = ["run_browser_task"]
