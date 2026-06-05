"""
JARVIS V3 — Workflow Schema (Pydantic)
──────────────────────────────────────────────────────────────
Defines the data model for YAML-based composable workflows.
A Workflow is a DAG of Nodes connected by Edges.
"""

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, ConfigDict


# ── Connection (edge) ─────────────────────────────────────


class Connection(BaseModel):
    """Directed edge between two nodes."""

    model_config = ConfigDict(populate_by_name=True)

    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")
    condition: Optional[str] = None  # e.g. "success", "failure", "always"


# ── Node configs ──────────────────────────────────────────


class TriggerConfig(BaseModel):
    trigger_type: Literal[
        "cron", "webhook", "file", "screen", "email", "git", "manual", "startup"
    ]
    # cron
    cron_expression: Optional[str] = None  # e.g. "0 8 * * 1-5"
    # webhook
    webhook_path: Optional[str] = None  # e.g. "/webhook/myflow"
    # file
    watch_path: Optional[str] = None
    # screen
    screen_event: Optional[str] = None  # e.g. "app_switch", "idle_5m"
    # email
    email_filter: Optional[str] = None
    # git
    git_repo: Optional[str] = None
    git_branch: Optional[str] = None


class ActionConfig(BaseModel):
    action_type: Literal["tool_call", "agent_task", "bash", "notify", "web_request"]
    # tool_call
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    # agent_task
    task_prompt: Optional[str] = None
    # bash
    command: Optional[str] = None
    # notify
    title: Optional[str] = None
    message: Optional[str] = None
    urgency: Optional[str] = "normal"
    # web_request
    url: Optional[str] = None
    method: Optional[str] = "GET"
    headers: Optional[Dict[str, str]] = None
    body: Optional[str] = None


class ConditionConfig(BaseModel):
    expression: str  # e.g. "{{ prev.output }} == 'ok'"


class LoopConfig(BaseModel):
    loop_type: Literal["for_each", "while", "retry"]
    items: Optional[str] = None  # var name or list expression
    max_retries: int = 3


class SubAgentConfig(BaseModel):
    specialist: str
    task: str
    timeout: int = 60


class AskUserConfig(BaseModel):
    question: str
    options: Optional[List[str]] = None


class CodeNodeConfig(BaseModel):
    code: str
    language: Literal["python", "bash"] = "python"


# ── Node ──────────────────────────────────────────────────


class Node(BaseModel):
    id: str
    type: Literal[
        "trigger", "action", "condition", "loop", "sub_agent", "ask_user", "code"
    ]
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


# ── Workflow ──────────────────────────────────────────────


class Workflow(BaseModel):
    name: str
    version: str = "1.0"
    description: Optional[str] = None
    nodes: List[Node]
    connections: List[Connection]

    def node_map(self) -> Dict[str, Node]:
        return {n.id: n for n in self.nodes}

    def children_of(self, node_id: str) -> List[str]:
        """Return IDs of children connected from node_id."""
        return [
            c.to_node
            for c in self.connections
            if c.from_node == node_id
        ]

    def parents_of(self, node_id: str) -> List[str]:
        """Return IDs of parents connected to node_id."""
        return [
            c.from_node
            for c in self.connections
            if c.to_node == node_id
        ]

    def topological_order(self) -> List[str]:
        """Return node IDs in DAG topological order."""
        in_degree: Dict[str, int] = {n.id: 0 for n in self.nodes}
        adj: Dict[str, List[str]] = {n.id: [] for n in self.nodes}
        for c in self.connections:
            adj[c.from_node].append(c.to_node)
            in_degree[c.to_node] = in_degree.get(c.to_node, 0) + 1

        queue = [n_id for n_id, deg in in_degree.items() if deg == 0]
        order: List[str] = []
        while queue:
            # deterministic sort for tests
            queue.sort()
            n_id = queue.pop(0)
            order.append(n_id)
            for child in adj.get(n_id, []):
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

        if len(order) != len(self.nodes):
            raise ValueError("Workflow contains a cycle — not a valid DAG")
        return order
