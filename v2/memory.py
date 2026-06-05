from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import KNOWLEDGE_FILE, GRAPH_FILE

_LOG = logging.getLogger(__name__)

# ── JSON Knowledge Store ──────────────────────────────────

_DEFAULTS = {
    "app_layouts":    {},   # {app: {element: {x, y}}}
    "learned_skills": {},   # {skill_name: [action_sequence]}
    "lessons":        [],   # [{context, mistake, fix, ts}]
    "user_prefs":     {},   # {pref_key: value}
    "routing_hints":  {},   # {task_pattern: preferred_model}
}


def load_knowledge() -> Dict[str, Any]:
    """Load knowledge from JSON file, applying defaults for missing keys.

    Returns:
        dict: Knowledge dictionary with all default keys ensured.
    """
    try:
        data = json.loads(Path(KNOWLEDGE_FILE).read_text())
        # Ensure all keys exist (graceful upgrade)
        for k, v in _DEFAULTS.items():
            data.setdefault(k, v)
        _LOG.debug("Loaded knowledge from %s", KNOWLEDGE_FILE)
        return data
    except Exception as e:
        _LOG.warning("Failed to load knowledge, using defaults: %s", e)
        return dict(_DEFAULTS)


def save_knowledge(k: Dict[str, Any]) -> None:
    """Save knowledge dictionary to JSON file.

    Args:
        k: Knowledge dictionary to persist.
    """
    try:
        Path(KNOWLEDGE_FILE).write_text(json.dumps(k, indent=2))
        _LOG.debug("Saved knowledge to %s", KNOWLEDGE_FILE)
    except Exception as e:
        _LOG.error("Failed to save knowledge: %s", e)


# ── Coordinate memory ─────────────────────────────────────

def learn_coordinate(app: str, element: str, x: int, y: int) -> str:
    """Learn and store a coordinate for an app element.

    Args:
        app: Application name.
        element: Element name within the app.
        x: X coordinate.
        y: Y coordinate.

    Returns:
        str: Confirmation message.
    """
    k = load_knowledge()
    k["app_layouts"].setdefault(app, {})[element] = {"x": x, "y": y}
    save_knowledge(k)
    msg = f"[MEM] Learned: {app}/{element} @ ({x},{y})"
    _LOG.info(msg)
    return msg


def get_coordinate(app: str, element: str) -> Optional[Dict[str, int]]:
    """Retrieve stored coordinate for an app element.

    Args:
        app: Application name.
        element: Element name within the app.

    Returns:
        dict with keys 'x' and 'y' if found, otherwise None.
    """
    coord = load_knowledge()["app_layouts"].get(app, {}).get(element)
    _LOG.debug("Retrieved coordinate for %s/%s: %s", app, element, coord)
    return coord


# ── Skill memory ──────────────────────────────────────────

def store_skill(name: str, steps: List[Any]) -> str:
    """Store a skill with its action sequence.

    Args:
        name: Skill identifier.
        steps: List of action steps constituting the skill.

    Returns:
        str: Confirmation message.
    """
    k = load_knowledge()
    k["learned_skills"][name] = {
        "steps": steps,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S")
    }
    save_knowledge(k)
    msg = f"[MEM] Skill '{name}' stored ({len(steps)} steps)"
    _LOG.info(msg)
    return msg


def get_skill(name: str) -> Optional[List[Any]]:
    """Retrieve the action steps for a stored skill.

    Args:
        name: Skill identifier.

    Returns:
        List of steps if skill exists, otherwise None.
    """
    skill = load_knowledge()["learned_skills"].get(name)
    steps = skill["steps"] if isinstance(skill, dict) else skill
    _LOG.debug("Retrieved skill %s: %s", name, steps)
    return steps


def list_skills() -> List[str]:
    """List all stored skill names.

    Returns:
        List of skill names.
    """
    skills = list(load_knowledge()["learned_skills"].keys())
    _LOG.debug("Listed %d skills", len(skills))
    return skills


# ── Lesson memory ─────────────────────────────────────────

def store_lesson(context: str, mistake: str, fix: str) -> str:
    """Store a lesson learned from a mistake.

    Args:
        context: Situation context.
        mistake: Description of the mistake.
        fix: Description of the fix or lesson.

    Returns:
        str: Confirmation message.
    """
    k = load_knowledge()
    k["lessons"].append({
        "context": context,
        "mistake": mistake,
        "fix": fix,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S")
    })
    # Cap at 200 lessons
    k["lessons"] = k["lessons"][-200:]
    save_knowledge(k)
    msg = f"[MEM] Lesson stored: {context[:50]}"
    _LOG.info(msg)
    return msg


def get_recent_lessons(n: int = 5) -> List[Dict[str, Any]]:
    """Retrieve the most recent lessons.

    Args:
        n: Number of recent lessons to return (default 5).

    Returns:
        List of lesson dictionaries, most recent last.
    """
    lessons = load_knowledge()["lessons"][-n:]
    _LOG.debug("Retrieved %d recent lessons", len(lessons))
    return lessons


def search_lessons(query: str) -> List[Dict[str, Any]]:
    """Search lessons for a query string in context or fix.

    Args:
        query: Search string (case-insensitive).

    Returns:
        List of matching lesson dictionaries (up to 5).
    """
    q = query.lower()
    matches = [
        l for l in load_knowledge()["lessons"]
        if q in l.get("context", "").lower() or q in l.get("fix", "").lower()
    ][:5]
    _LOG.debug("Search for '%s' returned %d matches", query, len(matches))
    return matches


# ── Knowledge Graph ────────────────────────────────────────

def _load_graph() -> Optional[Any]:
    """Load the NetworkX knowledge graph from pickle file.

    Returns:
        networkx.DiGraph if successful and library available, otherwise None.
    """
    try:
        import networkx as nx
        import pickle
        if Path(GRAPH_FILE).exists():
            with open(GRAPH_FILE, "rb") as f:
                return pickle.load(f)
        return nx.DiGraph()
    except ImportError:
        _LOG.warning("networkx not installed, graph functionality disabled")
        return None
    except Exception as e:
        _LOG.error("Failed to load graph: %s", e)
        return None


def _save_graph(G: Any) -> None:
    """Save the NetworkX knowledge graph to pickle file.

    Args:
        G: NetworkX DiGraph instance to save.
    """
    try:
        import pickle
        with open(GRAPH_FILE, "wb") as f:
            pickle.dump(G, f)
        _LOG.debug("Saved knowledge graph to %s", GRAPH_FILE)
    except Exception as e:
        _LOG.error("Failed to save graph: %s", e)


def add_knowledge_edge(source: str, relation: str, target: str, weight: float = 1.0) -> str:
    """Add a directed edge to the knowledge graph.

    Args:
        source: Source node label.
        relation: Relation label for the edge.
        target: Target node label.
        weight: Edge weight (default 1.0).

    Returns:
        str: Status message.
    """
    G = _load_graph()
    if G is None:
        msg = "[GRAPH] networkx not installed."
        _LOG.warning(msg)
        return msg
    G.add_edge(source.lower(), target.lower(),
               relation=relation, weight=weight,
               ts=time.strftime("%Y-%m-%dT%H:%M:%S"))
    _save_graph(G)
    msg = f"[GRAPH] {source} --[{relation}]--> {target}"
    _LOG.info(msg)
    return msg


def query_graph(node: str, depth: int = 2) -> str:
    """Query the knowledge graph for concepts within a depth of a node.

    Args:
        node: Node label to query around.
        depth: Maximum hop depth (default 2).

    Returns:
        str: Description of neighboring edges or status message.
    """
    G = _load_graph()
    if G is None or node.lower() not in G:
        msg = f"No graph knowledge about '{node}'."
        _LOG.debug(msg)
        return msg
    try:
        import networkx as nx
        sub = nx.ego_graph(G, node.lower(), radius=depth)
        edges = [
            f"{u} --[{d.get('relation','?')}]--> {v}"
            for u, v, d in sub.edges(data=True)
        ]
        if edges:
            result = f"Knowledge around '{node}':\n" + "\n".join(edges[:20])
        else:
            result = f"'{node}' is isolated."
        _LOG.debug("Queried graph for %s (depth=%d): %d edges found", node, depth, len(edges))
        return result
    except Exception as e:
        msg = f"[GRAPH ERROR] {e}"
        _LOG.error(msg)
        return msg


def get_related_concepts(node: str) -> List[str]:
    """Get direct neighbor nodes in the knowledge graph.

    Args:
        node: Node label to find neighbors for.

    Returns:
        List of neighbor node labels (empty if node not found or graph disabled).
    """
    G = _load_graph()
    if G is None or node.lower() not in G:
        _LOG.debug("No related concepts for %s (graph unavailable or node missing)", node)
        return []
    neighbors = list(G.neighbors(node.lower()))
    _LOG.debug("Found %d related concepts for %s", len(neighbors), node)
    return neighbors


# Define public API
__all__: List[str] = [
    "load_knowledge",
    "save_knowledge",
    "learn_coordinate",
    "get_coordinate",
    "store_skill",
    "get_skill",
    "list_skills",
    "store_lesson",
    "get_recent_lessons",
    "search_lessons",
    "add_knowledge_edge",
    "query_graph",
    "get_related_concepts",
]