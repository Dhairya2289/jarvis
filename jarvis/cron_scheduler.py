"""JARVIS Cron Scheduler

Natural-language cron with Telegram delivery.
Ported and adapted from Hermes Agent (MIT License).
Original: hermes/cron/scheduler.py + hermes/cron/jobs.py
"""
from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Final

from jarvis.config import BASE_DIR, TELEGRAM_TOKEN

_log = logging.getLogger(__name__)

CRON_DIR: Final[Path] = BASE_DIR / "cron"
JOBS_FILE: Final[Path] = CRON_DIR / "jobs.json"
OUTPUT_DIR: Final[Path] = CRON_DIR / "output"


ONESHOT_GRACE_SECONDS: Final[int] = 120

# In-process lock protecting load -> modify -> save cycles.
_jobs_lock = threading.Lock()


def _now() -> datetime:
    return datetime.now()


# ═══════════════════════════════════════════════════════════
#  Job model
# ═══════════════════════════════════════════════════════════
class CronJob:
    def __init__(
        self,
        name: str,  # Human-readable description
        schedule: str,  # e.g. "every day at 9am" or "*/5 * * * *"
        prompt: str,  # Task text sent to agent
        *,
        platform: str = "telegram",
        enabled: bool = True,
        job_id: str | None = None,
    ) -> None:
        self.id = job_id or str(uuid.uuid4())[:8]
        self.name = name
        self.schedule = schedule
        self.prompt = prompt
        self.platform = platform
        self.enabled = enabled
        self.created_at = _now().isoformat()
        self.last_run: str | None = None
        self.next_run: str | None = None
        self.run_count = 0
        self._parse_next_run()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "schedule": self.schedule,
            "prompt": self.prompt,
            "platform": self.platform,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "last_run": self.last_run,
            "next_run": self.next_run,
            "run_count": self.run_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CronJob:
        job = cls(
            name=data["name"],
            schedule=data["schedule"],
            prompt=data["prompt"],
            platform=data.get("platform", "telegram"),
            enabled=data.get("enabled", True),
            job_id=data["id"],
        )
        job.created_at = data.get("created_at", _now().isoformat())
        job.last_run = data.get("last_run")
        job.next_run = data.get("next_run")
        job.run_count = data.get("run_count", 0)
        return job

    def _parse_next_run(self) -> None:
        """Convert natural-language or cron-like schedule into a datetime."""
        if self.next_run is None:
            self.next_run = _parse_schedule(self.schedule).isoformat()

    def is_due(self) -> bool:
        if not self.enabled or self.next_run is None:
            return False
        return _now() >= datetime.fromisoformat(self.next_run)

    def mark_run(self, success: bool = True) -> None:
        self.last_run = _now().isoformat()
        self.run_count += 1
        if success:
            self._parse_next_run()


# ═══════════════════════════════════════════════════════════
#  Persistence
# ═══════════════════════════════════════════════════════════
def _load_jobs() -> list[CronJob]:
    CRON_DIR.mkdir(parents=True, exist_ok=True)
    if not JOBS_FILE.exists():
        return []
    try:
        data = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
        return [CronJob.from_dict(j) for j in data.get("jobs", [])]
    except Exception as exc:
        _log.error("Failed to load cron jobs: %s", exc)
        return []


def _save_jobs(jobs: list[CronJob]) -> None:
    CRON_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"jobs": [j.to_dict() for j in jobs]}
    tmp = JOBS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(JOBS_FILE)


# ═══════════════════════════════════════════════════════════
#  Natural-language schedule parser
# ═══════════════════════════════════════════════════════════
def _parse_schedule(schedule: str) -> datetime:
    """Convert a human-readable schedule into the next occurrence."""
    s = schedule.lower().strip()
    now = _now()

    # Every N minutes
    m = re.match(r"every\s+(\d+)\s*min(?:ute)?s?", s)
    if m:
        return now + timedelta(minutes=int(m.group(1)))

    # Every N hours
    m = re.match(r"every\s+(\d+)\s*hours?", s)
    if m:
        return now + timedelta(hours=int(m.group(1)))

    # Daily at HH:MM
    m = re.match(r"(?:daily|every day)\s+at\s+(\d{1,2}):(\d{2})", s)
    if m:
        target = now.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return target

    # Weekly on day at HH:MM
    days = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
    m = re.match(r"(?:weekly|every week)\s+on\s+(\w{3}).*?at\s+(\d{1,2}):(\d{2})", s)
    if m:
        target_day = days.get(m.group(1)[:3], 0)
        target = now.replace(hour=int(m.group(2)), minute=int(m.group(3)), second=0, microsecond=0)
        while target.weekday() != target_day or target <= now:
            target += timedelta(days=1)
        return target

    # Default: every 60 minutes
    _log.warning("Unrecognized schedule %r, defaulting to 60 minutes", schedule)
    return now + timedelta(minutes=60)


# ═══════════════════════════════════════════════════════════
#  Execution
# ═══════════════════════════════════════════════════════════
def _run_job(job: CronJob) -> str:
    """Execute the agent task for a single job."""
    from jarvis.agent import run_agent

    _log.info("[CRON] Executing job %s: %s", job.id, job.name)
    try:
        result = run_agent(job.prompt)
        _save_output(job.id, result)
        if job.platform == "telegram" and TELEGRAM_TOKEN:
            _send_telegram(f"⏰ *Cron: {job.name}*\n\n{result[:2000]}")
        job.mark_run(success=True)
        return result
    except Exception as exc:
        _log.error("[CRON] Job %s failed: %s", job.id, exc, exc_info=True)
        _save_output(job.id, f"[ERROR] {exc}")
        job.mark_run(success=False)
        return f"[ERROR] {exc}"


def _save_output(job_id: str, text: str) -> None:
    out_dir = OUTPUT_DIR / job_id
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = _now().strftime("%Y-%m-%dT%H-%M-%S")
    (out_dir / f"{ts}.md").write_text(text, encoding="utf-8")


def _send_telegram(text: str) -> None:
    try:
        import requests
        from jarvis.config import ALLOWED_USER_IDS
        if not ALLOWED_USER_IDS:
            return
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": ALLOWED_USER_IDS[0], "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
    except Exception:
        _log.debug("Telegram send failed", exc_info=True)


# ═══════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════
def add_job(name: str, schedule: str, prompt: str, **kwargs: Any) -> str:
    """Add a new cron job. Returns the job ID."""
    with _jobs_lock:
        jobs = _load_jobs()
        job = CronJob(name=name, schedule=schedule, prompt=prompt, **kwargs)
        jobs.append(job)
        _save_jobs(jobs)
    info = f"[CRON] Added job #{job.id}: {name} → {schedule}"
    _log.info(info)
    return info


def remove_job(job_id: str) -> str:
    """Remove a cron job by ID."""
    with _jobs_lock:
        jobs = _load_jobs()
        before = len(jobs)
        jobs = [j for j in jobs if j.id != job_id]
        if len(jobs) == before:
            return f"[CRON] Job #{job_id} not found."
        _save_jobs(jobs)
    info = f"[CRON] Removed job #{job_id}."
    _log.info(info)
    return info


def list_jobs() -> str:
    """Return a human-readable list of all jobs."""
    jobs = _load_jobs()
    if not jobs:
        return "📋 No cron jobs scheduled."
    lines = ["📋 Cron Jobs:"]
    for j in jobs:
        status = "✅" if j.enabled else "🛑"
        next_run = j.next_run[:16] if j.next_run else "?"
        lines.append(
            f"  {status} #{j.id} {j.name}\n"
            f"     Schedule: {j.schedule} | Next: {next_run} | Runs: {j.run_count}"
        )
    return "\n".join(lines)


def tick() -> str:
    """Check all jobs and execute any that are due.

    Called every 60 seconds from a background thread.
    Returns a summary string.
    """
    with _jobs_lock:
        jobs = _load_jobs()
        due = [j for j in jobs if j.is_due()]
        if not due:
            return "[CRON] No jobs due."
        results = []
        for job in due:
            result = _run_job(job)
            results.append(f"#{job.id}: {result[:100]}")
        _save_jobs(jobs)
    return "\n".join(f"[CRON] {r}" for r in results)


def main() -> None:
    """Run the scheduler loop."""
    _log.info("Cron scheduler started (tick every 60s)")
    import time
    try:
        while True:
            summary = tick()
            if "No jobs due" not in summary:
                _log.info(summary)
            time.sleep(60)
    except KeyboardInterrupt:
        _log.info("Cron scheduler stopped.")


__all__ = [
    "add_job",
    "remove_job",
    "list_jobs",
    "tick",
    "main",
    "CronJob",
]
