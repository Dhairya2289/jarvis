"""Sync ↔ Async bridge utilities for JARVIS V2↔V3 interop.

V2 modules are (mostly) synchronous.  V3 is async-first.  These helpers let
V2 callers invoke V3 async code and vice-versa without manually managing
``asyncio`` internals.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from functools import wraps
from typing import Any, Callable, Coroutine, TypeVar

F = TypeVar("F", bound=Callable[..., Any])
_log = logging.getLogger(__name__)


def to_sync(async_func: Callable[..., Coroutine[Any, Any, Any]]) -> Callable[..., Any]:
    """Turn an async function into a sync-callable wrapper.

    If called from outside a running event loop, ``asyncio.run()`` is used.
    If called from *inside* a running loop, the coroutine is dispatched to a
    background thread and executed there (each thread gets its own loop).
    """
    @wraps(async_func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        coro = async_func(*args, **kwargs)
        try:
            loop = asyncio.get_running_loop()
            _log.debug("to_sync: dispatching %s to background thread", async_func.__name__)
            return thread_run(coro)
        except RuntimeError:
            _log.debug("to_sync: running %s via asyncio.run", async_func.__name__)
            return asyncio.run(coro)
    return wrapper


def to_async(sync_func: Callable[..., Any]) -> Callable[..., Coroutine[Any, Any, Any]]:
    """Turn a sync function into an async one (no-op wrapper)."""
    @wraps(sync_func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        return sync_func(*args, **kwargs)
    return wrapper


def thread_run(coro: Coroutine[Any, Any, Any], timeout: float = 30.0) -> Any:
    """Run *coro* in a dedicated thread and return its result.

    This is safe to call even when an event loop is already running in the
    current thread because each worker thread spawns its own fresh loop.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result(timeout=timeout)


__all__ = ["to_sync", "to_async", "thread_run"]
