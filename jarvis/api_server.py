"""JARVIS HTTP API — Remote Control Layer

Exposes Jarvis as a FastAPI server for remote triggers.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import subprocess
import time
from datetime import datetime, timedelta
from typing import Final

from fastapi import FastAPI, Header, HTTPException, UploadFile, File
from jose import jwt, JWTError
from pydantic import BaseModel

from jarvis.agent import run_agent

_log = logging.getLogger(__name__)

app = FastAPI(title="JARVIS API", version="2.0")

SECRET_KEY = os.environ.get("JARVIS_JWT_SECRET", "change-me-in-production")
ALGORITHM: Final[str] = "HS256"

MACHINES: dict[str, str] = {}


def create_token(device_name: str, expires_hours: int = 24) -> str:
    data = {
        "sub": device_name,
        "exp": datetime.utcnow() + timedelta(hours=expires_hours),
    }
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str | None) -> str:
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload["sub"]
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


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
    verify_token(x_token)

    start = time.time()
    try:
        result = await asyncio.wait_for(
            run_agent(req.task, session_id=req.session_id),
            timeout=120.0,
        )
        return TaskResponse(
            result=result,
            elapsed_s=round(time.time() - start, 1),
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Agent timed out")
    except HTTPException:
        raise
    except Exception as exc:
        _log.error("Agent crashed during API call: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Agent error: {exc}"
        ) from exc


@app.post("/voice-input")
async def voice_input(audio: UploadFile = File(...), x_token: str = Header(None)):
    """Accept audio from phone, transcribe, run agent."""
    verify_token(x_token)
    audio_bytes = await audio.read()
    from jarvis.voice.transcriber import transcribe_bytes

    text = transcribe_bytes(audio_bytes)
    result = await run_agent(text)
    return {"text": text, "result": result}


@app.get("/screenshot")
async def get_screenshot(x_token: str = Header(None)):
    """Return current desktop screenshot as base64."""
    verify_token(x_token)
    subprocess.run(
        ["grim", "/tmp/jarvis_phone_screen.png"],
        check=True,
        timeout=5,
    )
    with open("/tmp/jarvis_phone_screen.png", "rb") as f:
        img = base64.b64encode(f.read()).decode()
    return {"image": img}


@app.post("/click")
async def remote_click(x: int, y: int, x_token: str = Header(None)):
    """Click at coordinates from phone."""
    verify_token(x_token)
    subprocess.run(
        ["ydotool", "mousemove", "--absolute", str(x), str(y)],
        check=True,
        timeout=3,
    )
    subprocess.run(
        ["ydotool", "click", "0xC0"],
        check=True,
        timeout=3,
    )
    return {"status": "clicked"}


@app.get("/machines")
async def machines(x_token: str = Header(None)):
    verify_token(x_token)
    return {"machines": list(MACHINES.keys())}


@app.get("/machine/{name}/health")
async def machine_health(name: str, x_token: str = Header(None)):
    verify_token(x_token)
    return {"name": name, "status": "ok"}


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


__all__ = ["app", "main", "create_token", "verify_token"]
