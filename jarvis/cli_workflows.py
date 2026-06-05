"""
JARVIS V3 — Workflow CLI Commands
──────────────────────────────────────────────────────────────
`jarvis-v3 workflow run <file>`  — execute workflow once
`jarvis-v3 workflow schedule <file>` — register cron triggers
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from jarvis.workflows.loader import load_workflow
from jarvis.workflows.engine import WorkflowEngine
from jarvis.workflows.scheduler import WorkflowScheduler


_scheduler: WorkflowScheduler | None = None


def workflow_cli():
    parser = argparse.ArgumentParser(prog="jarvis-v3 workflow")
    sub = parser.add_subparsers(dest="cmd")

    # run
    run_p = sub.add_parser("run", help="Execute a workflow once")
    run_p.add_argument("file", help="Path to workflow YAML")
    run_p.add_argument("--node", default="", help="Start from this node ID")

    # schedule
    sched_p = sub.add_parser("schedule", help="Register cron triggers from workflow")
    sched_p.add_argument("file", help="Path to workflow YAML")

    # list
    list_p = sub.add_parser("list", help="List scheduled workflow jobs")

    args = parser.parse_args(sys.argv[2:] if len(sys.argv) > 2 else [])

    if args.cmd == "run":
        try:
            wf = load_workflow(args.file)
            engine = WorkflowEngine(wf)
            result = asyncio.run(engine.run(args.node))
            print(json.dumps(result, indent=2, default=str))
        except Exception as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            sys.exit(1)

    elif args.cmd == "schedule":
        global _scheduler
        if _scheduler is None:
            _scheduler = WorkflowScheduler()
        try:
            jobs = _scheduler.register(args.file)
            _scheduler.start()
            print(f"Scheduled {len(jobs)} job(s):")
            for jid in jobs:
                print(f"  • {jid}")
        except Exception as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            sys.exit(1)

    elif args.cmd == "list":
        if _scheduler is None:
            print("No scheduler running.")
            return
        jobs = _scheduler.list_jobs()
        if not jobs:
            print("No scheduled jobs.")
            return
        print("Scheduled jobs:")
        for jid, info in jobs.items():
            print(f"  • {jid}: {info}")
    else:
        parser.print_help()


if __name__ == "__main__":
    workflow_cli()
