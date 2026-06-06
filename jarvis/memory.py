"""JARVIS Knowledge Graph — Minimal V3 port of V2 memory module."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

GRAPH_FILE: Path = Path.home() / ".jarvis" / "knowledge_graph.pkl"
KNOWLEDGE_FILE: Path = Path.home() / ".jarvis" / "knowledge.json"


def _load_graph() -> Any | None:
    try:
        import pickle
        if GRAPH_FILE.exists():
            with open(GRAPH_FILE, "rb") as fh:
                return pickle.load(fh)
        import networkx as nx
        return nx.DiGraph()
    except ImportError:
        _log.warning("networkx not installed, graph disabled")
        return None
    except Exception as exc:
        _log.error("Failed to load graph: %s", exc)
        return None


def _save_graph(graph: Any) -> None:
    try:
        import pickle
        GRAPH_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(GRAPH_FILE, "wb") as fh:
            pickle.dump(graph, fh)
    except Exception as exc:
        _log.error("Failed to save graph: %s", exc)


def add_knowledge_edge(source: str, relation: str, target: str, weight: float = 1.0) -> str:
    """Add a directed edge to the knowledge graph."""
    G = _load_graph()
    if G is None:
        msg = "[GRAPH] networkx not installed."
        _log.warning(msg)
        return msg
    G.add_edge(
        source.lower(),
        target.lower(),
        relation=relation,
        weight=weight,
        ts=time.strftime("%Y-%m-%dT%H:%M:%S"),
    )
    _save_graph(G)
    msg = f"[GRAPH] {source} --[{relation}]--> {target}"
    _log.info(msg)
    return msg


def load_knowledge() -> dict:
    """Load the full knowledge dict from JSON file."""
    try:
        if KNOWLEDGE_FILE.exists():
            return json.loads(KNOWLEDGE_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        _log.warning("Failed to load knowledge: %s", exc)
    return {
        "app_layouts": {},
        "learned_skills": {},
        "lessons": [],
        "user_prefs": {},
    }


def save_knowledge(k: dict) -> None:
    """Persist knowledge dict to JSON file."""
    try:
        KNOWLEDGE_FILE.parent.mkdir(parents=True, exist_ok=True)
        KNOWLEDGE_FILE.write_text(json.dumps(k, indent=2), encoding="utf-8")
    except Exception as exc:
        _log.error("Failed to save knowledge: %s", exc)


__all__ = ["add_knowledge_edge", "load_knowledge", "save_knowledge"]
