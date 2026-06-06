"""JARVIS GUI API routes — served under /api/*."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from jarvis.config import BASE_DIR

router = APIRouter()

# ── helpers ──────────────────────────────────────────────────────────────────

PSUTIL_AVAILABLE = False
try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    pass


def _run_sync(sync_fn, *args, **kwargs):
    """Run a blocking sync function in a thread pool (safe for async routes)."""
    return asyncio.to_thread(sync_fn, *args, **kwargs)


# ── GET /api/health ──────────────────────────────────────────────────────────


@router.get("/health")
async def health():
    """Return system stats in the dashboard format."""
    try:
        # CPU
        cpu_pct = psutil.cpu_percent(interval=0.1) if PSUTIL_AVAILABLE else 0.0

        # Memory
        mem = psutil.virtual_memory() if PSUTIL_AVAILABLE else None
        if mem:
            mem_used_gb = round(mem.used / (1024**3), 1)
            mem_total_gb = round(mem.total / (1024**3), 1)
            mem_str = f"{mem_used_gb}G / {mem_total_gb}G"
        else:
            mem_str = "unavailable"

        # Disk
        disk = psutil.disk_usage("/") if PSUTIL_AVAILABLE else None
        if disk:
            disk_used_gb = round(disk.used / (1024**3), 0)
            disk_total_gb = round(disk.total / (1024**3), 0)
            disk_str = f"{disk_used_gb:.0f}G / {disk_total_gb:.0f}G"
        else:
            disk_str = "unavailable"

        cpu_str = f"{cpu_pct:.0f}%" if isinstance(cpu_pct, float) else str(cpu_pct)

        return JSONResponse({
            "cpu": cpu_str,
            "memory": mem_str,
            "disk": disk_str,
            "jarvis_pid": os.getpid(),
        })
    except Exception as e:
        return JSONResponse({"cpu": "?", "memory": "?", "disk": "?", "jarvis_pid": os.getpid(), "error": str(e)})


# ── GET /api/model ───────────────────────────────────────────────────────────


@router.get("/model")
async def model_status():
    """Return Ollama model status from ~/.jarvis/.env or localhost:11434."""
    model_name = "unknown"
    # Try reading from .env
    env_path = Path.home() / ".jarvis" / ".env"
    if env_path.exists():
        try:
            for line in env_path.read_text().splitlines():
                if line.startswith("OLLAMA_MODEL="):
                    model_name = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
        except Exception:
            pass

    status = "stopped"
    last_trained = datetime.now().strftime("%Y-%m-%d")

    # Try hitting Ollama API
    try:
        import httpx

        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get("http://localhost:11434/api/tags")
            if resp.status_code == 200:
                status = "running"
                data = resp.json()
                models = data.get("models", [])
                if models and model_name == "unknown":
                    # Use first available model as fallback display name
                    model_name = models[0].get("name", "unknown")
    except Exception:
        # Ollama not reachable — that's fine, report as stopped
        pass

    return JSONResponse({
        "model": model_name,
        "status": status,
        "last_trained": last_trained,
    })


# ── GET /api/tasks ───────────────────────────────────────────────────────────


@router.get("/tasks")
async def tasks():
    """Return smart todos from the Obsidian inbox."""
    try:
        def _load():
            from jarvis.smart_todo import SmartTodo

            vault = Path.home() / "Documents" / "vault"
            if not vault.exists():
                vault = BASE_DIR / "vault"
            todo = SmartTodo(vault)
            return todo.list_items("open"), todo.list_items("done")

        open_items, done_items = await _run_sync(_load)

        return JSONResponse({
            "open": len(open_items),
            "done": len(done_items),
            "items": [
                {
                    "text": item.text,
                    "priority": item.priority.value if hasattr(item.priority, "value") else str(item.priority),
                    "due": item.due,
                }
                for item in open_items
            ],
        })
    except Exception as e:
        return JSONResponse({"open": 0, "done": 0, "items": [], "error": str(e)})


# ── GET /api/desktop ─────────────────────────────────────────────────────────


@router.get("/desktop")
async def desktop():
    """Return workspace snapshot and active window info."""
    try:
        def _load():
            from jarvis.desktop.workspace_memory import WorkspaceMemory
            from jarvis.desktop.window_logger import WindowLogger

            ws = WorkspaceMemory().snapshot()
            wl = WindowLogger()
            event = wl.tick()
            return ws, event

        workspaces, window_event = await _run_sync(_load)

        return JSONResponse({
            "workspaces": len(workspaces),
            "active_window": window_event.title if window_event else "none",
            "active_class": window_event.class_name if window_event else "none",
        })
    except Exception as e:
        return JSONResponse({"workspaces": 0, "active_window": "error", "active_class": "", "error": str(e)})


# ── GET /api/clipboard ───────────────────────────────────────────────────────


@router.get("/clipboard")
async def clipboard():
    """Return recent clipboard history."""
    try:
        def _load():
            from jarvis.desktop.clipboard_history import ClipboardHistory

            return ClipboardHistory().get_recent(10)

        recent = await _run_sync(_load)

        return JSONResponse({
            "recent": recent,
            "count": len(recent),
        })
    except Exception as e:
        return JSONResponse({"recent": [], "count": 0, "error": str(e)})


# ── GET /api/notifications ───────────────────────────────────────────────────


@router.get("/notifications")
async def notifications():
    """Return recent desktop notifications."""
    try:
        def _load():
            from jarvis.desktop.notification_triage import NotificationTriage

            return NotificationTriage().recent(10)

        recent = await _run_sync(_load)

        return JSONResponse({
            "recent": [n.to_dict() for n in recent],
            "count": len(recent),
        })
    except Exception as e:
        return JSONResponse({"recent": [], "count": 0, "error": str(e)})


# ── GET /api/rss ─────────────────────────────────────────────────────────────


@router.get("/rss")
async def rss():
    """Return RSS digest for the last 24 hours."""
    try:
        def _load():
            from jarvis.rss_reader import RSSReader

            vault = Path.home() / "Documents" / "vault"
            feeds_path = BASE_DIR / "feeds.txt"
            feeds = []
            if feeds_path.exists():
                feeds = [line.strip() for line in feeds_path.read_text().splitlines() if line.strip()]
            reader = RSSReader(BASE_DIR / "rss.db", feeds)
            since = datetime.now() - timedelta(days=1)
            digest = reader.get_digest(since)
            return digest

        digest = await _run_sync(_load)

        # Parse simple markdown digest into structured entries
        entries = []
        for line in digest.splitlines():
            if line.startswith("- ["):
                # e.g. "- [Title](url) [feed_name · date]"
                parts = line[2:].split("]", 1)
                if parts:
                    title = parts[0]
                    feed = "unknown"
                    if "[" in parts[1]:
                        feed_part = parts[1].split("[")[1].split("·")[0].strip()
                        feed = feed_part
                    entries.append({"title": title, "feed": feed})
                if len(entries) >= 10:
                    break

        return JSONResponse({
            "entries": entries,
            "count": len(entries),
        })
    except Exception as e:
        return JSONResponse({"entries": [], "count": 0, "error": str(e)})


# ── GET /api/memory ──────────────────────────────────────────────────────────


@router.get("/memory")
async def memory():
    """Return recent memories from MemDir."""
    try:
        def _load():
            from jarvis.memdir import MemDir

            memdir = MemDir()
            entries = memdir.search("", limit=10)
            return entries

        entries = await _run_sync(_load)

        return JSONResponse({
            "entries": [
                {
                    "content": e.content[:200],
                    "type": e.mem_type,
                }
                for e in entries
            ],
            "count": len(entries),
        })
    except Exception as e:
        return JSONResponse({"entries": [], "count": 0, "error": str(e)})


# ── POST /api/action ─────────────────────────────────────────────────────────


@router.post("/action")
async def action(body: dict):
    """Dispatch a named tool action."""
    action_name = body.get("action", "")
    if not action_name:
        raise HTTPException(status_code=400, detail="action field is required")

    # Map friendly names to dispatch_tool keys
    _ACTION_MAP = {
        "snapshot": "snapshot_workspace",
        "organize_downloads": "organize_downloads",
        "index_files": "universal_search",
        "archive_screenshots": "archive_screenshots",
    }

    tool_name = _ACTION_MAP.get(action_name, action_name)

    try:
        from jarvis.tools import dispatch_tool

        result = await _run_sync(dispatch_tool, tool_name, {})

        ok = not str(result).startswith("[ERROR]")
        return JSONResponse({
            "ok": ok,
            "message": result,
        })
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)})


# ── Chat (streaming via Ollama) ───────────────────────────

@router.post("/chat")
async def chat(body: dict):
    """Stream chat completions from the local JARVIS model."""
    messages = body.get("messages", [])
    model = body.get("model", "jarvis-custom-v2")

    async def event_stream():
        import httpx, json as _json
        async with httpx.AsyncClient() as client:
            payload = {
                "model": model,
                "messages": messages,
                "stream": True,
                "options": {"num_predict": 300},
            }
            async with client.stream("POST", "http://localhost:11434/api/chat", json=payload, timeout=60) as resp:
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = _json.loads(line)
                        content = chunk.get("message", {}).get("content", "")
                        if content:
                            yield f"data: {_json.dumps({'content': content})}\n\n"
                    except Exception:
                        pass
                yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── Real-time SSE stream ─────────────────────────────────

@router.get("/stream")
async def stream():
    """Server-Sent Events pushing real-time system updates."""
    async def event_generator():
        import json as _json, asyncio as _asyncio
        while True:
            try:
                data = {}
                # Health
                try:
                    import psutil
                    data["health"] = {
                        "cpu": f"{psutil.cpu_percent(interval=0.1)}%",
                        "memory": f"{psutil.virtual_memory().used // (1024**3)}G / {psutil.virtual_memory().total // (1024**3)}G",
                        "disk": f"{psutil.disk_usage('/').used // (1024**3)}G / {psutil.disk_usage('/').total // (1024**3)}G",
                    }
                except Exception:
                    data["health"] = {"cpu": "?", "memory": "?", "disk": "?"}

                # Active window
                try:
                    from jarvis.desktop.window_logger import WindowLogger
                    tick = WindowLogger().tick()
                    data["desktop"] = {
                        "active_window": tick.get("title", "?") if tick else "?",
                        "active_class": tick.get("class", "?") if tick else "?",
                    }
                except Exception:
                    data["desktop"] = {"active_window": "?"}

                # Task count
                try:
                    from jarvis.smart_todo import SmartTodo
                    vault = Path.home() / "obsidian" / "JARVIS"
                    todos = SmartTodo(vault).list_items("open")
                    data["tasks"] = {"open": len(todos)}
                except Exception:
                    data["tasks"] = {"open": 0}

                # Notifications
                try:
                    from jarvis.desktop.notification_triage import NotificationTriage
                    notifs = NotificationTriage().recent(5)
                    data["notifications"] = {"count": len(notifs)}
                except Exception:
                    data["notifications"] = {"count": 0}

                yield f"data: {_json.dumps(data)}\n\n"
                await _asyncio.sleep(3)
            except Exception:
                await _asyncio.sleep(3)

    return StreamingResponse(event_generator(), media_type="text/event-stream")