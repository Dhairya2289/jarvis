"""Watch clipboard content and send brief proactive insights for copied errors/code."""
from __future__ import annotations

import logging
import subprocess
import time
from typing import Final

import requests

from jarvis.config import ALLOWED_USER_IDS, FCC_AUTH_TOKEN, FCC_BASE_URL, TELEGRAM_TOKEN

_log = logging.getLogger(__name__)

_MARKERS: Final[list[str]] = [
    "Exception", "Traceback", "Error", "def ", "import ", "main(",
]


class InsightClient:
    """Generate clipboard insights using the configured LLM backend."""

    def __init__(self) -> None:
        self._model: str | None = None

    def _detect_model(self) -> str:
        if self._model is not None:
            return self._model
        try:
            from jarvis.config import DEFAULT_MODEL
            self._model = DEFAULT_MODEL
        except Exception:
            self._model = "gemini/models/gemini-2.0-flash-lite"
        return self._model

    def send_telegram(self, text: str) -> None:
        if not TELEGRAM_TOKEN or not ALLOWED_USER_IDS:
            _log.info("[CLIP] %s", text)
            return
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={
                    "chat_id": ALLOWED_USER_IDS[0],
                    "text": text,
                    "parse_mode": "Markdown",
                },
                timeout=8,
            )
        except Exception:
            _log.debug("Telegram send failed", exc_info=True)

    def analyze(self, content: str) -> None:
        if len(content) < 10:
            return
        if not any(marker in content for marker in _MARKERS):
            return

        prompt = (
            "The user copied this code/error. Provide one short useful tip if it "
            "looks actionable. If not useful, reply IGNORE.\n\n"
            f"{content[:4000]}"
        )
        try:
            import anthropic
            client = anthropic.Anthropic(
                base_url=FCC_BASE_URL, api_key=FCC_AUTH_TOKEN
            )
            response = client.messages.create(
                model=self._detect_model(),
                max_tokens=100,
                messages=[{"role": "user", "content": prompt}],
            )
            answer = response.content[0].text.strip()
            if "IGNORE" not in answer.upper():
                self.send_telegram(f"Clipboard Insight: {answer}")
        except Exception:
            _log.debug("Insight generation failed", exc_info=True)


def _paste() -> str:
    try:
        return subprocess.run(
            ["wl-paste"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except subprocess.TimeoutExpired:
        _log.warning("wl-paste timed out after 5s - clipboard may be locked")
        return ""
    except Exception:
        return ""


def watch_clipboard() -> None:
    """Poll clipboard every 2 seconds and analyze new content."""
    client = InsightClient()
    _log.info("Watching clipboard")
    last_clip = _paste()
    while True:
        current = _paste()
        if current and current != last_clip:
            last_clip = current
            client.analyze(current)
        time.sleep(2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    watch_clipboard()


__all__ = ["InsightClient", "watch_clipboard"]
