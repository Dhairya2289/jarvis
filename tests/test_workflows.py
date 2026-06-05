"""
Tests for jarvis workflows
──────────────────────────────────────────────────────────────
Covers schema, loader, engine, and scheduler.
"""

import asyncio
from pathlib import Path

import pytest

from jarvis.workflows.schema import Workflow, Node, Connection
from jarvis.workflows.loader import load_workflow
from jarvis.workflows.engine import WorkflowEngine


def _run(coro):
    return asyncio.run(coro)


# ── Schema ────────────────────────────────────────────────


def test_workflow_topological_order():
    wf = Workflow(
        name="test",
        nodes=[
            Node(id="a", type="trigger"),
            Node(id="b", type="action"),
            Node(id="c", type="action"),
        ],
        connections=[
            Connection(from_node="a", to_node="b"),
            Connection(from_node="b", to_node="c"),
        ],
    )
    order = wf.topological_order()
    assert order == ["a", "b", "c"]


def test_workflow_cycle_detection():
    wf = Workflow(
        name="cycle",
        nodes=[
            Node(id="a", type="trigger"),
            Node(id="b", type="action"),
        ],
        connections=[
            Connection(from_node="a", to_node="b"),
            Connection(from_node="b", to_node="a"),
        ],
    )
    with pytest.raises(ValueError, match="cycle"):
        wf.topological_order()


# ── Loader ────────────────────────────────────────────────


def test_load_morning_brief(tmp_path: Path):
    src = Path(__file__).parent.parent / "v3" / "examples" / "workflows" / "morning_brief.yaml"
    if not src.exists():
        pytest.skip("morning_brief.yaml not found")
    wf = load_workflow(src)
    assert wf.name == "morning_brief"
    assert len(wf.nodes) >= 2
    assert wf.node_map()["trigger"].type == "trigger"


def test_load_invalid_yaml(tmp_path: Path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("not a mapping")
    with pytest.raises(ValueError):
        load_workflow(bad)


# ── Engine ────────────────────────────────────────────────


def test_engine_tool_call():
    wf = Workflow(
        name="echo",
        nodes=[
            Node(
                id="t1",
                type="trigger",
                config={"trigger_type": "manual"},
            ),
            Node(
                id="a1",
                type="action",
                config={
                    "action_type": "tool_call",
                    "tool_name": "bash",
                    "tool_args": {"command": "echo hello_workflow"},
                },
            ),
        ],
        connections=[Connection(from_node="t1", to_node="a1")],
    )
    engine = WorkflowEngine(wf)
    result = _run(engine.run())
    assert "hello_workflow" in str(result)


def test_engine_notify_action():
    wf = Workflow(
        name="notify",
        nodes=[
            Node(
                id="t1",
                type="trigger",
                config={"trigger_type": "manual"},
            ),
            Node(
                id="a1",
                type="action",
                config={
                    "action_type": "notify",
                    "title": "Test",
                    "message": "Hello",
                },
            ),
        ],
        connections=[Connection(from_node="t1", to_node="a1")],
    )
    engine = WorkflowEngine(wf)
    result = _run(engine.run())
    assert "Notification sent" in str(result)


def test_engine_condition():
    wf = Workflow(
        name="cond",
        nodes=[
            Node(
                id="t1",
                type="trigger",
                config={"trigger_type": "manual"},
            ),
            Node(
                id="c1",
                type="condition",
                config={"expression": "True"},
            ),
            Node(
                id="a1",
                type="action",
                config={
                    "action_type": "tool_call",
                    "tool_name": "bash",
                    "tool_args": {"command": "echo pass"},
                },
            ),
        ],
        connections=[
            Connection(from_node="t1", to_node="c1"),
            Connection(from_node="c1", to_node="a1"),
        ],
    )
    engine = WorkflowEngine(wf)
    result = _run(engine.run())
    # Condition should have been evaluated and stored
    assert "pass" in str(result) or "True" in str(result)


def test_engine_code_python():
    wf = Workflow(
        name="code",
        nodes=[
            Node(
                id="t1",
                type="trigger",
                config={"trigger_type": "manual"},
            ),
            Node(
                id="c1",
                type="code",
                config={
                    "code": "result = 2 + 2",
                    "language": "python",
                },
            ),
        ],
        connections=[Connection(from_node="t1", to_node="c1")],
    )
    engine = WorkflowEngine(wf)
    result = _run(engine.run())
    assert "executed" in str(result) or "4" in str(result)


# ── CLI (smoke) ───────────────────────────────────────────


def test_cli_workflow_imports():
    from jarvis.cli_workflows import workflow_cli
    assert callable(workflow_cli)