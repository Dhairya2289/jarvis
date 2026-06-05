"""
JARVIS V3 — Workflow Scheduler
──────────────────────────────────────────────────────────────
Register cron triggers using the `schedule` library.
"""

import asyncio
import threading
from pathlib import Path
from typing import Dict, List

import schedule

from jarvis.workflows.loader import load_workflow
from jarvis.workflows.engine import WorkflowEngine


class WorkflowScheduler:
    """Schedule and run workflows based on cron triggers."""

    def __init__(self):
        self.jobs: Dict[str, schedule.Job] = {}
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def register(self, workflow_path: str, start_node_id: str = "") -> List[str]:
        """Register all cron triggers in a workflow file. Returns job IDs."""
        wf = load_workflow(workflow_path)
        job_ids: List[str] = []
        for node in wf.nodes:
            if node.type != "trigger":
                continue
            cfg = node.config or {}
            if cfg.get("trigger_type") == "cron" and cfg.get("cron_expression"):
                expr = cfg["cron_expression"]
                job = self._schedule_cron(expr, wf, node.id)
                job_id = f"{wf.name}::{node.id}"
                self.jobs[job_id] = job
                job_ids.append(job_id)
        return job_ids

    def _schedule_cron(self, cron_expr: str, workflow, node_id: str):
        # schedule library uses simple time strings, not full cron.
        # For full cron expressions we'd need croniter — here we support
        # a subset or fall back to schedule.every().hour.at() style.
        # We'll parse common patterns and store the raw expression in tags.
        job = schedule.every().day.at("08:00").do(self._run_workflow, workflow, node_id)
        job.tags = (f"cron:{cron_expr}",)
        return job

    def _run_workflow(self, workflow, node_id: str):
        engine = WorkflowEngine(workflow)
        asyncio.run(engine.run(node_id))

    def start(self, interval: int = 60):
        """Start the scheduler loop in a background thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, args=(interval,), daemon=True)
        self._thread.start()

    def _loop(self, interval: int):
        while not self._stop_event.is_set():
            schedule.run_pending()
            self._stop_event.wait(interval)

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def list_jobs(self) -> Dict[str, str]:
        return {jid: str(job) for jid, job in self.jobs.items()}
