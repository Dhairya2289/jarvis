"""
Tests for coordinator.py — Multi-Agent Task Coordinator
"""

from __future__ import annotations

import pytest

from jarvis.coordinator import Coordinator, CoordinatorResult, Subtask


# ── Fixtures ────────────────────────────────────────────────


@pytest.fixture
def coordinator() -> Coordinator:
    return Coordinator()


# ── Decompose tests ─────────────────────────────────────────


class TestDecompose:
    def test_decompose_single_task(self, coordinator: Coordinator):
        subtasks = coordinator.decompose("What is the capital of France?")
        assert len(subtasks) == 1
        assert subtasks[0].description == "What is the capital of France?"
        assert subtasks[0].specialist in ("agent", "tools")

    def test_decompose_and_split(self, coordinator: Coordinator):
        subtasks = coordinator.decompose(
            "Write a Python script and test it"
        )
        assert len(subtasks) >= 2
        combined = " ".join(s.description for s in subtasks).lower()
        assert "python" in combined or "script" in combined

    def test_decompose_newline_split(self, coordinator: Coordinator):
        subtasks = coordinator.decompose(
            "First task\nSecond task"
        )
        assert len(subtasks) >= 2

    def test_decompose_compare_vs(self, coordinator: Coordinator):
        subtasks = coordinator.decompose("Compare Linux vs BSD")
        assert len(subtasks) >= 2
        # Each subtask should cover one side
        descriptions = " ".join(s.description.lower() for s in subtasks)
        assert "linux" in descriptions or "bsd" in descriptions

    def test_decompose_versus(self, coordinator: Coordinator):
        subtasks = coordinator.decompose("Compare Arch versus Debian")
        assert len(subtasks) >= 2

    def test_decompose_empty_returns_empty(self, coordinator: Coordinator):
        assert coordinator.decompose("") == []
        assert coordinator.decompose("   ") == []

    def test_decompose_all_have_unique_ids(self, coordinator: Coordinator):
        subtasks = coordinator.decompose("one and two and three")
        ids = [s.id for s in subtasks]
        assert len(ids) == len(set(ids))

    def test_decompose_sets_status_pending(self, coordinator: Coordinator):
        subtasks = coordinator.decompose("Do something")
        assert all(s.status == "pending" for s in subtasks)

    def test_decompose_specialist_assignment(self, coordinator: Coordinator):
        subtasks = coordinator.decompose("Run bash command to list files")
        assert all(s.specialist == "tools" for s in subtasks)

    def test_decompose_multiple_and_split(self, coordinator: Coordinator):
        subtasks = coordinator.decompose(
            "write code and test it and deploy it"
        )
        # Should produce at least 2 subtasks
        assert len(subtasks) >= 2


# ── Execute parallel tests ──────────────────────────────────


class TestExecuteParallel:
    def test_execute_sets_status_done(self, coordinator: Coordinator):
        subtasks = [
            Subtask(id="s1", description="What is 2+2?", specialist="agent"),
        ]
        results = coordinator.execute_parallel(subtasks)
        assert results[0].status == "done"

    def test_execute_multiple_in_parallel(self, coordinator: Coordinator):
        subtasks = [
            Subtask(id="s1", description="Say hello", specialist="agent"),
            Subtask(id="s2", description="Say world", specialist="agent"),
        ]
        results = coordinator.execute_parallel(subtasks)
        assert len(results) == 2
        assert all(s.status == "done" for s in results)

    def test_execute_tools_specialist(self, coordinator: Coordinator):
        subtasks = [
            Subtask(
                id="t1",
                description="echo 'hello from tools'",
                specialist="tools",
            ),
        ]
        results = coordinator.execute_parallel(subtasks)
        assert results[0].status == "done"
        assert "hello" in results[0].result.lower() or "[ERROR]" in results[0].result

    def test_execute_preserves_order(self, coordinator: Coordinator):
        subtasks = [
            Subtask(id="s1", description="First", specialist="agent"),
            Subtask(id="s2", description="Second", specialist="agent"),
        ]
        results = coordinator.execute_parallel(subtasks)
        assert results[0].id == "s1"
        assert results[1].id == "s2"


# ── Merge tests ─────────────────────────────────────────────


class TestMerge:
    def test_merge_empty(self):
        result = Coordinator.merge([])
        assert "No results" in result

    def test_merge_single_subtask(self):
        st = Subtask(id="s1", description="test task", specialist="agent", status="done", result="OK")
        result = Coordinator.merge([st])
        assert "Results" in result
        assert "Summary" in result
        assert "test task" in result
        assert "OK" in result

    def test_merge_multiple_subtasks(self):
        st1 = Subtask(id="s1", description="Task One", specialist="agent", status="done", result="One OK")
        st2 = Subtask(id="s2", description="Task Two", specialist="agent", status="done", result="Two OK")
        result = Coordinator.merge([st1, st2])
        assert "Task One" in result
        assert "Task Two" in result
        assert "Subtask 1" in result
        assert "Subtask 2" in result

    def test_merge_shows_error_status(self):
        st = Subtask(id="s1", description="Failing task", specialist="agent", status="error", result="boom")
        result = Coordinator.merge([st])
        assert "ERROR" in result

    def test_merge_summary_counts(self):
        done = Subtask(id="s1", description="Good", specialist="agent", status="done", result="OK")
        err = Subtask(id="s2", description="Bad", specialist="agent", status="error", result="NO")
        result = Coordinator.merge([done, err])
        assert "1/2" in result or "1 subtask" in result.lower()
        assert "error" in result.lower() or "Error" in result


# ── Full run pipeline ───────────────────────────────────────


class TestRun:
    def test_run_returns_coordinator_result(self, coordinator: Coordinator):
        result = coordinator.run("What is 1+1?")
        assert isinstance(result, CoordinatorResult)
        assert result.original_task == "What is 1+1?"
        assert result.duration_ms >= 0

    def test_run_has_subtasks(self, coordinator: Coordinator):
        result = coordinator.run("Do this and that")
        assert len(result.subtasks) >= 1

    def test_run_merged_result_is_markdown(self, coordinator: Coordinator):
        result = coordinator.run("Say hello")
        assert "# Results" in result.merged_result
        assert "# Summary" in result.merged_result

    def test_run_duration_ms_reasonably_sized(self, coordinator: Coordinator):
        result = coordinator.run("Simple task")
        assert result.duration_ms >= 0
        assert result.duration_ms < 60000  # sanity cap

    def test_run_decompose_and_execute_integration(self, coordinator: Coordinator):
        """Complex task → decompose → execute → merge must not raise."""
        result = coordinator.run("write a python script and test it")
        assert result.merged_result is not None
        assert len(result.subtasks) >= 1