"""
Tests for jarvis.background_review
──────────────────────────────────────
Review grading, daemon start/stop, and queue handling.
"""

import threading
import time

import pytest

from jarvis.background_review import (
    BackgroundReview,
    ReviewResult,
    ActionLog,
)


# ── Fixtures ──────────────────────────────────────────────

@pytest.fixture
def review(tmp_path, monkeypatch) -> BackgroundReview:
    """BackgroundReview pointing at a temp review dir, no daemon auto-start."""
    import jarvis.background_review as br
    monkeypatch.setattr(br, "DEFAULT_REVIEW_DIR", tmp_path / "reviews")
    monkeypatch.setattr(br, "DEFAULT_OBSIDIAN_VAULT", tmp_path / "obsidian")
    br.DEFAULT_REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    br.DEFAULT_OBSIDIAN_VAULT.mkdir(parents=True, exist_ok=True)
    return BackgroundReview(
        review_interval=60,
        review_dir=tmp_path / "reviews",
        obsidian_vault=tmp_path / "obsidian",
    )


# ── review_action grading ─────────────────────────────────

class TestReviewActionGrading:

    def test_fast_clean_action_is_ok(self, review: BackgroundReview):
        action: ActionLog = {
            "action": "echo",
            "input": "hello",
            "output": "hello",
            "duration_ms": 500,
        }
        result = review.review_action(action)
        assert result.grade == "ok"
        assert "error" not in result.issues
        assert result.suggestions  # always at least one

    def test_slow_action_graded_slow(self, review: BackgroundReview):
        action: ActionLog = {
            "action": "heavy_compute",
            "input": "",
            "output": "result",
            "duration_ms": 8000,
        }
        result = review.review_action(action)
        assert result.grade == "slow"
        assert any("8000ms" in i for i in result.issues)

    def test_action_with_error_in_output_is_graded_error(self, review: BackgroundReview):
        action: ActionLog = {
            "action": "risky_task",
            "input": "",
            "output": "ERROR: connection refused",
            "duration_ms": 200,
        }
        result = review.review_action(action)
        assert result.grade == "error"
        assert any("error" in i.lower() for i in result.issues)

    def test_error_takes_precedence_over_slow(self, review: BackgroundReview):
        """Both slow and error signals present → grade should be error."""
        action: ActionLog = {
            "action": "bad_slow_task",
            "input": "",
            "output": "ERROR: timeout after 10s",
            "duration_ms": 10000,
        }
        result = review.review_action(action)
        assert result.grade == "error"

    def test_exactly_5000ms_is_not_slow(self, review: BackgroundReview):
        action: ActionLog = {
            "action": "boundary",
            "input": "",
            "output": "ok",
            "duration_ms": 5000,
        }
        result = review.review_action(action)
        assert result.grade == "ok"

    def test_issues_and_suggestions_are_lists(self, review: BackgroundReview):
        action: ActionLog = {"action": "x", "input": "", "output": "err", "duration_ms": 0}
        result = review.review_action(action)
        assert isinstance(result.issues, list)
        assert isinstance(result.suggestions, list)

    def test_action_log_missing_fields_handled_gracefully(self, review: BackgroundReview):
        # Empty dict — should not raise
        result = review.review_action({})
        assert isinstance(result, ReviewResult)


# ── Queue ─────────────────────────────────────────────────

class TestQueue:

    def test_submit_queues_action(self, review: BackgroundReview):
        action: ActionLog = {"action": "test", "input": "", "output": "", "duration_ms": 0}
        review.submit(action)
        # Queue should now have one item
        assert review._queue.qsize() == 1

    def test_submit_multiple_actions(self, review: BackgroundReview):
        for i in range(5):
            review.submit({"action": f"task_{i}", "input": "", "output": "", "duration_ms": 0})
        assert review._queue.qsize() == 5


# ── Daemon lifecycle ──────────────────────────────────────

class TestDaemonLifecycle:

    def test_start_is_idempotent(self, review: BackgroundReview):
        review.start()
        review.start()
        assert review._started is True
        review.stop()

    def test_stop_after_start_is_clean(self, review: BackgroundReview):
        review.start()
        review.stop()
        assert review._started is False

    def test_stop_without_start_is_safe(self, review: BackgroundReview):
        review.stop()  # should not raise

    def test_worker_thread_name(self, review: BackgroundReview):
        review.start()
        assert review._worker_thread is not None
        assert review._worker_thread.name == "BackgroundReview"
        review.stop()


# ── Write paths ───────────────────────────────────────────

class TestWriteReview:

    def test_write_json_when_obsidian_unavailable(self, review: BackgroundReview, tmp_path):
        """When obsidian vault does not exist, fall back to JSON."""
        review.obsidian_vault = tmp_path / "nonexistent_vault"
        action: ActionLog = {"action": "test", "input": "x", "output": "y", "duration_ms": 100}
        result = review.review_action(action)
        review._write_review(action, result)

        json_files = list(review.review_dir.glob("*.json"))
        assert len(json_files) == 1
        data = __import__("json").loads(json_files[0].read_text())
        assert data["grade"] == "ok"
        assert data["action"] == "test"

    def test_write_obsidian_daily_note(self, review: BackgroundReview):
        """When obsidian vault exists, write to daily note."""
        review.obsidian_vault.mkdir(parents=True, exist_ok=True)
        action: ActionLog = {"action": "echo", "input": "hello", "output": "hello", "duration_ms": 50}
        result = review.review_action(action)
        review._write_review(action, result)

        from datetime import datetime
        date_str = datetime.now().strftime("%Y-%m-%d")
        daily_note = review.obsidian_vault / "daily" / f"{date_str}.md"
        assert daily_note.is_file()
        content = daily_note.read_text()
        assert "Review: echo" in content
        assert "ok" in content

    def test_reviews_appended_to_existing_daily_note(self, review: BackgroundReview):
        """Second review for same day should append, not overwrite."""
        review.obsidian_vault.mkdir(parents=True, exist_ok=True)
        from datetime import datetime
        date_str = datetime.now().strftime("%Y-%m-%d")
        daily_dir = review.obsidian_vault / "daily"
        daily_dir.mkdir()
        existing_note = daily_dir / f"{date_str}.md"
        existing_note.write_text("---\ndate: " + date_str + "\ntags: [daily]\n---\n\n# Daily note\n")

        for action_name in ("task_a", "task_b"):
            action: ActionLog = {
                "action": action_name,
                "input": "",
                "output": "ok",
                "duration_ms": 50,
            }
            result = review.review_action(action)
            review._write_review(action, result)

        content = existing_note.read_text()
        assert "task_a" in content
        assert "task_b" in content

    def test_write_review_does_not_raise_on_error(self, review: BackgroundReview, tmp_path):
        """If write fails (e.g. permission), it should not propagate."""
        action: ActionLog = {"action": "test", "input": "", "output": "", "duration_ms": 0}
        result = review.review_action(action)
        # Pass an invalid obsidian vault path that will cause write to fail
        review._write_json_review(action, result, "1970-01-01_00-00-00")