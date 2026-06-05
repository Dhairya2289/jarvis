"""JARVIS Queue Worker

Background process that periodically checks and executes queued tasks.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Final

from jarvis.queue_manager import process_queue

_log = logging.getLogger(__name__)

_CHECK_INTERVAL: Final[int] = 60


async def worker_loop() -> None:
    """Run the queue worker forever."""
    _log.info("Queue worker started (interval=%ss).", _CHECK_INTERVAL)
    while True:
        try:
            count = await process_queue()
            if count > 0:
                _log.info("Processed %d task(s).", count)
        except Exception:
            _log.error("Worker error", exc_info=True)
        await asyncio.sleep(_CHECK_INTERVAL)


def main() -> None:
    try:
        asyncio.run(worker_loop())
    except KeyboardInterrupt:
        _log.info("Queue worker stopped by user.")


if __name__ == "__main__":
    main()


__all__ = ["worker_loop", "main"]
