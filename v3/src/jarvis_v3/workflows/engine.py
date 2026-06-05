"""
JARVIS V3 — Workflow Engine
──────────────────────────────────────────────────────────────
Execute a Workflow DAG node-by-node.
Nodes: trigger → action → condition → loop → sub_agent → ask_user → code
"""

import asyncio
import json
from typing import Any, Dict, List

from jarvis_v3.workflows.schema import Workflow, Node
from jarvis_v3.tools import dispatch_tool
from jarvis_v3.config import MAX_TOKENS


class WorkflowEngine:
    """Execute a workflow DAG."""

    def __init__(self, workflow: Workflow):
        self.workflow = workflow
        self.context: Dict[str, Any] = {"outputs": {}}

    async def run(self, start_node_id: str = "") -> Dict[str, Any]:
        """Run workflow from start_node_id (or first trigger node)."""
        order = self.workflow.topological_order()

        if start_node_id:
            if start_node_id not in order:
                raise ValueError(f"Start node '{start_node_id}' not in workflow")
            idx = order.index(start_node_id)
            order = order[idx:]
        else:
            # Find first trigger node, or just run all
            triggers = [n.id for n in self.workflow.nodes if n.type == "trigger"]
            if triggers:
                first_trigger = triggers[0]
                if first_trigger in order:
                    idx = order.index(first_trigger)
                    order = order[idx:]

        for node_id in order:
            node = self.workflow.node_map()[node_id]
            await self._execute_node(node)

        return self.context

    async def _execute_node(self, node: Node) -> Any:
        """Execute a single node and store its output."""
        cfg = node.config or {}
        node_type = node.type
        result: Any = None

        if node_type == "trigger":
            result = {"triggered": True, "type": cfg.get("trigger_type", "manual")}

        elif node_type == "action":
            result = await self._run_action(cfg)

        elif node_type == "condition":
            result = self._eval_condition(cfg)

        elif node_type == "loop":
            result = await self._run_loop(cfg)

        elif node_type == "sub_agent":
            result = await self._run_sub_agent(cfg)

        elif node_type == "ask_user":
            result = await self._run_ask_user(cfg)

        elif node_type == "code":
            result = await self._run_code(cfg)

        else:
            result = {"error": f"Unknown node type: {node_type}"}

        self.context["outputs"][node.id] = result
        return result

    async def _run_action(self, cfg: Dict[str, Any]) -> Any:
        action_type = cfg.get("action_type", "tool_call")

        if action_type == "tool_call":
            tool_name = cfg.get("tool_name", "")
            tool_args = cfg.get("tool_args", {})
            args = dict(tool_args)
            # simple template substitution
            for k, v in args.items():
                if isinstance(v, str) and "{{" in v:
                    for node_id, out in self.context["outputs"].items():
                        placeholder = f"{{{{ {node_id} }}}}"
                        if placeholder in v:
                            v = v.replace(placeholder, str(out))
                    args[k] = v
            return dispatch_tool(tool_name, args)

        elif action_type == "agent_task":
            prompt = cfg.get("task_prompt", "")
            from jarvis_v3.agent import run_agent
            return await run_agent(prompt)

        elif action_type == "bash":
            cmd = cfg.get("command", "")
            return dispatch_tool("bash", {"command": cmd})

        elif action_type == "notify":
            return dispatch_tool(
                "desktop_notification",
                {
                    "title": cfg.get("title", "JARVIS Workflow"),
                    "message": cfg.get("message", ""),
                    "urgency": cfg.get("urgency", "normal"),
                },
            )

        elif action_type == "web_request":
            return await self._web_request(cfg)

        return {"error": f"Unknown action type: {action_type}"}

    def _eval_condition(self, cfg: Dict[str, Any]) -> bool:
        expr = cfg.get("expression", "")
        # Simple template substitution into Python eval
        for node_id, out in self.context["outputs"].items():
            placeholder = f"{{{{ {node_id} }}}}"
            if placeholder in expr:
                expr = expr.replace(placeholder, json.dumps(out))
        try:
            # SECURITY: eval is dangerous. Restrict builtins.
            result = eval(expr, {"__builtins__": {}}, {})
            return bool(result)
        except Exception as e:
            return False

    async def _run_loop(self, cfg: Dict[str, Any]) -> List[Any]:
        loop_type = cfg.get("loop_type", "for_each")
        results: List[Any] = []

        if loop_type == "for_each":
            items_expr = cfg.get("items", "")
            # resolve variable or literal list
            try:
                items = eval(items_expr)
            except Exception:
                items = []
            for item in items:
                # Each iteration we could run child nodes, but for simplicity
                # we just execute a configured action
                action_cfg = cfg.get("action", {})
                action_cfg = dict(action_cfg)
                if "tool_args" in action_cfg:
                    for k, v in action_cfg["tool_args"].items():
                        if isinstance(v, str) and "{{ item }}" in v:
                            action_cfg["tool_args"][k] = v.replace("{{ item }}", str(item))
                results.append(await self._run_action(action_cfg))

        elif loop_type == "retry":
            max_retries = cfg.get("max_retries", 3)
            action_cfg = cfg.get("action", {})
            for attempt in range(max_retries):
                try:
                    res = await self._run_action(action_cfg)
                    if not str(res).startswith("[ERROR]"):
                        return [res]
                    results.append(res)
                except Exception as e:
                    results.append(str(e))
            return results

        return results

    async def _run_sub_agent(self, cfg: Dict[str, Any]) -> str:
        from jarvis_v3.agent import run_agent
        specialist = cfg.get("specialist", "general")
        task = cfg.get("task", "")
        return await run_agent(f"[{specialist}] {task}")

    async def _run_ask_user(self, cfg: Dict[str, Any]) -> str:
        question = cfg.get("question", "")
        options = cfg.get("options")
        if options:
            opts = "/".join(options)
            print(f"[ASK_USER] {question} ({opts})")
        else:
            print(f"[ASK_USER] {question}")
        return {"question": question, "options": options, "awaiting_input": True}

    async def _run_code(self, cfg: Dict[str, Any]) -> Any:
        code = cfg.get("code", "")
        language = cfg.get("language", "python")
        if language == "bash":
            return dispatch_tool("bash", {"command": code})
        # python
        try:
            local_vars = {"context": self.context, "outputs": self.context["outputs"]}
            exec(code, {"__builtins__": __builtins__}, local_vars)
            return local_vars.get("result", "executed")
        except Exception as e:
            return f"[ERROR] {e}"

    async def _web_request(self, cfg: Dict[str, Any]) -> Any:
        import httpx
        url = cfg.get("url", "")
        method = cfg.get("method", "GET")
        headers = cfg.get("headers", {})
        body = cfg.get("body")
        try:
            async with httpx.AsyncClient() as client:
                if method == "GET":
                    r = await client.get(url, headers=headers, timeout=15)
                elif method == "POST":
                    r = await client.post(url, headers=headers, content=body, timeout=15)
                else:
                    r = await client.request(method, url, headers=headers, content=body, timeout=15)
                return {"status": r.status_code, "text": r.text[:2000]}
        except Exception as e:
            return {"error": str(e)}
