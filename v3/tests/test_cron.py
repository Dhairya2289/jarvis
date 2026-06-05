"""Tests for cron_scheduler module."""
from __future__ import annotations

import pytest

from jarvis_v3.cron_scheduler import CronJob, add_job, list_jobs, remove_job, _parse_schedule


class TestCronJob:
    def test_parse_schedule_minutes(self):
        job = CronJob("test", "every 5 minutes", "do thing")
        assert job.schedule == "every 5 minutes"

    def test_parse_schedule_daily(self):
        job = CronJob("test", "daily at 14:30", "do thing")
        assert job.schedule == "daily at 14:30"

    def test_to_dict_roundtrip(self):
        job = CronJob("test", "every 10 minutes", "prompt")
        d = job.to_dict()
        restored = CronJob.from_dict(d)
        assert restored.name == job.name
        assert restored.schedule == job.schedule


class TestParseSchedule:
    def test_every_minutes(self):
        import datetime as dt
        result = _parse_schedule("every 5 minutes")
        assert isinstance(result, dt.datetime)
        assert result > dt.datetime.now()

    def test_daily(self):
        import datetime as dt
        result = _parse_schedule("daily at 9:00")
        assert isinstance(result, dt.datetime)
        assert result.hour == 9

    def test_weekly(self):
        import datetime as dt
        result = _parse_schedule("weekly on mon at 9:00")
        assert isinstance(result, dt.datetime)


class TestCronApi:
    def test_add_and_list(self):
        result = add_job("test_job", "every 60 minutes", "echo hello")
        assert "Added" in result
        listing = list_jobs()
        assert "test_job" in listing

    def test_remove(self):
        add_job("removable", "every 60 minutes", "echo hi")
        listing = list_jobs()
        import re
        match = re.search(r"#(\w+)", listing)
        assert match
        job_id = match.group(1)
        result = remove_job(job_id)
        assert "Removed" in result
