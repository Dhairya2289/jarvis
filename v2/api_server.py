"""JARVIS HTTP API — Remote Control Layer

Exposes Jarvis as a FastAPI server for remote triggers.
"""
from __future__ import annotations

import logging
import time
from typing import Final

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from agent import run_agent
from config import JARVIS_API_TOKEN

_log = logging.getLogger(__name__)

app = FastAPI(title="JARVIS API", version="2.0")

API_TOKEN: Final[str] = JARVIS_API_TOKEN


class TaskRequest(BaseModel):
    task: str
    session_id: str = "api_remote"


class TaskResponse(BaseModel):
    result: str
    elapsed_s: float
    error: str | None = None


@app.post("/task", response_model=TaskResponse)
async def execute_task(
    req: TaskRequest,
    x_token: str | None = Header(None),
) -> TaskResponse:
    """Execute a single task via the agent and return the result."""
    if x_token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid API token")

    start = time.time()
    try:
        result = run_agent(req.task, session_id=req.session_id)
        return TaskResponse(
            result=result,
            elapsed_s=round(time.time() - start, 1),
        )
    except HTTPException:
        raise
    except Exception as exc:
        _log.error("Agent crashed during API call: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Agent error: {exc}"
        ) from exc


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "online", "identity": "JARVIS V2"}


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "JARVIS API", "docs": "/docs"}


def main() -> None:
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8090, log_level="info")


if __name__ == "__main__":
    main()


__all__ = ["app", "main"]
