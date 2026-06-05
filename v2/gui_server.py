"""
JARVIS V2 HUD server.

Serves the standalone HUD and bridges browser commands to the live agent with
server-sent events. The server deliberately avoids SocketIO so the HUD can run
with only Flask on the backend and vanilla browser APIs on the frontend.
"""
from __future__ import annotations

import json
import os
import queue
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, request, send_file, stream_with_context

try:
    import psutil
except Exception:  # pragma: no cover - optional at import time
    psutil = None


ROOT = Path(__file__).resolve().parent
TASKS: dict[str, "queue.Queue[dict[str, Any]]"] = {}
TASK_LOCK = threading.Lock()

app = Flask(__name__)


def _event(event: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"event": event, "data": data}


def _put(task_id: str, event: str, data: dict[str, Any]) -> None:
    with TASK_LOCK:
        q = TASKS.get(task_id)
    if q:
        q.put(_event(event, data))


def _run_task(task_id: str, command: str) -> None:
    start = time.time()

    def status(message: str) -> None:
        _put(task_id, "status", {"message": str(message), "elapsed_s": round(time.time() - start, 1)})

    def token(delta: str) -> None:
        _put(task_id, "token", {"delta": str(delta)})

    try:
        status("Agent bootstrapping...")
        from agent import run_agent

        result = run_agent(command, status_callback=status, token_callback=token, session_id="hud")
        _put(task_id, "result", {"result": result, "elapsed_s": round(time.time() - start, 1)})
    except Exception as exc:
        _put(task_id, "agent_error", {"error": f"{type(exc).__name__}: {exc}"})
    finally:
        _put(task_id, "done", {"elapsed_s": round(time.time() - start, 1)})


@app.get("/")
def index():
    return send_file(ROOT / "jarvis-hud.html")


@app.get("/api/health")
def health():
    return jsonify({
        "ok": True,
        "cwd": str(ROOT),
        "pid": os.getpid(),
        "agent": "jarvis-v2",
    })


@app.get("/api/stats")
def stats():
    if psutil is None:
        return jsonify({"ok": False, "error": "psutil is not installed"}), 503

    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    net = psutil.net_io_counters()
    cpu_cores = psutil.cpu_percent(interval=None, percpu=True)
    temp_c = None

    try:
        temps = psutil.sensors_temperatures()
        for entries in temps.values():
            if entries:
                temp_c = entries[0].current
                break
    except Exception:
        temp_c = None

    return jsonify({
        "ok": True,
        "cpu": psutil.cpu_percent(interval=None),
        "cpu_cores": cpu_cores[:8],
        "ram": mem.percent,
        "ram_used_gb": round(mem.used / (1024 ** 3), 1),
        "ram_total_gb": round(mem.total / (1024 ** 3), 1),
        "swap": swap.percent,
        "swap_used_gb": round(swap.used / (1024 ** 3), 1),
        "temp_c": temp_c,
        "net_sent": net.bytes_sent,
        "net_recv": net.bytes_recv,
        "tasks": len(TASKS),
    })


@app.post("/api/command")
def command():
    payload = request.get_json(silent=True) or {}
    command_text = str(payload.get("command", "")).strip()
    if not command_text:
        return jsonify({"ok": False, "error": "Empty command"}), 400

    task_id = uuid.uuid4().hex
    with TASK_LOCK:
        TASKS[task_id] = queue.Queue()

    worker = threading.Thread(target=_run_task, args=(task_id, command_text), daemon=True)
    worker.start()

    return jsonify({"ok": True, "task_id": task_id})


@app.get("/api/events/<task_id>")
def events(task_id: str):
    with TASK_LOCK:
        q = TASKS.get(task_id)
    if q is None:
        return jsonify({"ok": False, "error": "Unknown task"}), 404

    @stream_with_context
    def generate():
        try:
            while True:
                try:
                    item = q.get(timeout=20)
                except queue.Empty:
                    yield "event: ping\ndata: {}\n\n"
                    continue

                yield f"event: {item['event']}\n"
                yield f"data: {json.dumps(item['data'])}\n\n"

                if item["event"] == "done":
                    break
        finally:
            with TASK_LOCK:
                TASKS.pop(task_id, None)

    return Response(generate(), mimetype="text/event-stream")


if __name__ == "__main__":
    print("[JARVIS HUD] http://127.0.0.1:5050")
    app.run(host="127.0.0.1", port=5050, threaded=True, debug=False)
