"""Tests for jarvis_v3.compat.bridge utilities."""
from __future__ import annotations

import asyncio

import pytest

from jarvis_v3.compat.bridge import to_async, to_sync, thread_run


async def _sample_async(x: int) -> int:
    await asyncio.sleep(0)
    return x * 2


def _sample_sync(x: int) -> int:
    return x * 3


class TestToAsync:
    @pytest.mark.anyio
    async def test_wraps_sync(self):
        wrapped = to_async(_sample_sync)
        result = await wrapped(5)
        assert result == 15


class TestToSync:
    def test_runs_async(self):
        wrapped = to_sync(_sample_async)
        result = wrapped(5)
        assert result == 10

    def test_runs_async_from_async_context(self):
        async def inner():
            wrapped = to_sync(_sample_async)
            return wrapped(7)

        # When called inside an async context, to_sync dispatches to a
        # background thread; it does not block the current loop.
        result = asyncio.run(inner())
        assert result == 14


class TestThreadRun:
    def test_runs_coro(self):
        result = thread_run(_sample_async(4))
        assert result == 8
