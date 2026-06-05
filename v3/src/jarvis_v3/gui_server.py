"""
JARVIS V3 — HUD Backend Server
──────────────────────────────────────────────────────────────
Serves real-time system stats and health endpoints for the HUD.
FastAPI-based with CORS for local file access.
"""

import os
import time
from pathlib import Path

from jarvis_v3.config import BASE_DIR

# ── FastAPI guard (user may not have installed deps yet) ──
try:
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
    from fastapi.middleware.cors import CORSMiddleware
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    FastAPI = Request = object  # type: ignore

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


def get_agent_states() -> list:
    """Return current agent/specialist states."""
    return [
        {"id": "ALPHA-01", "name": "TaskRouter", "task": "Polling queue", "status": "active", "cpu": 2},
        {"id": "BETA-07", "name": "CodeGen", "task": "Ready", "status": "active", "cpu": 0},
        {"id": "GAMMA-03", "name": "WebScraper", "task": "Rate-limited", "status": "busy", "cpu": 8},
        {"id": "DELTA-04", "name": "Researcher", "task": "Web search", "status": "busy", "cpu": 14},
        {"id": "EPS-02", "name": "FileSysWatch", "task": "Watching", "status": "active", "cpu": 1},
        {"id": "ZETA-05", "name": "MemoryMgr", "task": "Compacting", "status": "busy", "cpu": 5},
        {"id": "ETA-06", "name": "VoiceProc", "task": "Standby", "status": "idle", "cpu": 0},
        {"id": "THETA-08", "name": "Scheduler", "task": "Idle", "status": "idle", "cpu": 0},
    ]


def get_system_stats() -> dict:
    """Gather live system stats via psutil."""
    if not PSUTIL_AVAILABLE:
        return {
            "ok": False,
            "error": "psutil not installed",
            "cpu": 0.0,
            "ram_pct": 0.0,
            "swap_pct": 0.0,
            "temp": 0,
            "net_up": 0,
            "net_down": 0,
            "cpu_cores": [],
        }

    cpu_percent = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory()
    swap = psutil.swap_memory()

    try:
        temp = psutil.sensors_temperatures()
        temps = []
        for name, entries in temp.items():
            for e in entries:
                if e.current is not None:
                    temps.append(e.current)
        avg_temp = round(sum(temps) / len(temps), 1) if temps else 0
    except Exception:
        avg_temp = 0

    try:
        net = psutil.net_io_counters()
        net_sent = net.bytes_sent
        net_recv = net.bytes_recv
    except Exception:
        net_sent = net_recv = 0

    return {
        "ok": True,
        "cpu": float(cpu_percent),
        "ram_pct": float(ram.percent),
        "ram_used_gb": round(ram.used / 1024 / 1024 / 1024, 1),
        "ram_total_gb": round(ram.total / 1024 / 1024 / 1024, 1),
        "swap_pct": float(swap.percent),
        "swap_used_gb": round(swap.used / 1024 / 1024 / 1024, 1),
        "temp": float(avg_temp) if avg_temp else 0,
        "cpu_cores": [round(p, 1) for p in psutil.cpu_percent(percpu=True, interval=0.1)],
        "net_up": net_sent,
        "net_down": net_recv,
        "gpu": 0.0,
    }


# ── Build FastAPI app ─────────────────────────────────────

if FASTAPI_AVAILABLE:
    app = FastAPI(title="JARVIS HUD", version="3.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app = None  # type: ignore


if FASTAPI_AVAILABLE and app is not None:
    @app.get("/api/health")
    async def health():
        return JSONResponse({"ok": True, "pid": os.getpid(), "version": "3.0"})

    @app.get("/api/stats")
    async def stats():
        return JSONResponse(get_system_stats())

    @app.get("/api/agents")
    async def agents():
        return JSONResponse(get_agent_states())

    @app.post("/api/command")
    async def command(request: Request):
        try:
            body = await request.json()
            cmd = body.get("command", "")
            # Execute via agent
            import asyncio
            from jarvis_v3.agent import run_agent
            result = await run_agent(cmd)
            return JSONResponse({"ok": True, "result": result})
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)})

    @app.get("/")
    async def root():
        hud_path = Path(__file__).parent.parent.parent / "static" / "hud.html"
        if hud_path.exists():
            return FileResponse(str(hud_path))
        return JSONResponse({"msg": "JARVIS HUD backend running. Open /static/hud.html"})

    @app.get("/api/stream")
    async def stream():
        import asyncio

        async def event_generator():
            while True:
                s = get_system_stats()
                entry = {
                    "timestamp": time.time() * 1000,
                    "level": "INFO",
                    "message": f"CPU: {s['cpu']:.1f}% | RAM: {s['ram_pct']:.1f}%",
                }
                yield f"data: {entry}\n\n"
                await asyncio.sleep(2)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
        )


def run_server(host: str = "127.0.0.1", port: int = 8765):
    """Entry point for `jarvis-v3 --hud`."""
    if not FASTAPI_AVAILABLE:
        print("[ERROR] FastAPI not installed. Run: pip install fastapi uvicorn")
        return
    import uvicorn

    uvicorn.run("jarvis_v3.gui_server:app", host=host, port=port, reload=False)
