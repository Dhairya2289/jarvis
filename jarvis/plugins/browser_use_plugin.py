"""Browser-use integration plugin for JARVIS V3.

Provides high-level web-automation primitives via the browser-use library.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

_log = logging.getLogger(__name__)


def _lazy_imports() -> tuple[Any, Any]:
    try:
        from browser_use import Agent, Browser
        return Agent, Browser
    except ImportError as exc:
        raise RuntimeError(
            "browser-use is not installed. Run: pip install browser-use"
        ) from exc


async def browse(
    task: str,
    *,
    model: str = "gpt-4o",
    headless: bool = True,
) -> str:
    """Run a browser-use Agent to accomplish *task* on the web.

    Args:
        task: Natural-language instruction (e.g. "Find the price of NVDA").
        model: LLM model identifier for the agent.
        headless: Whether to hide the browser window.

    Returns:
        Agent result text.
    """
    Agent, Browser = _lazy_imports()
    browser = Browser()
    agent = Agent(
        task=task,
        llm=model,
        browser=browser,
    )
    try:
        result = await agent.run()
        return str(result)
    finally:
        await browser.close()


def run_sync(task: str, **kwargs: Any) -> str:
    """Synchronous wrapper around :func:`browse`."""
    try:
        loop = asyncio.get_running_loop()
        # Already in async context — dispatch to a fresh thread loop
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, browse(task, **kwargs))
            return future.result(timeout=120)
    except RuntimeError:
        return asyncio.run(browse(task, **kwargs))


__all__ = ["browse", "run_sync"]
