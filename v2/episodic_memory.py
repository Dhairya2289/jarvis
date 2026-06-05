from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, List, Dict, Optional

from config import CHROMA_DIR

_LOG = logging.getLogger(__name__)

# Lazy-import ChromaDB so missing dep doesn't crash everything
def _get_collection() -> Optional[Any]:
    """Get the ChromaDB collection for episodic memory.

    Returns:
        ChromaDB collection instance if available, otherwise None.
    """
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        return client.get_or_create_collection(
            name="jarvis_episodes",
            metadata={"hnsw:space": "cosine"}
        )
    except ImportError:
        _LOG.warning("ChromaDB not installed, episodic memory disabled")
        return None
    except Exception as e:
        _LOG.error("Failed to get ChromaDB collection: %s", e)
        return None


def store_successful_task(intent: str, actions: List[Any]) -> str:
    """Save a successful (intent, actions) pair to vector DB.

    Args:
        intent: The task intent or goal.
        actions: List of actions taken to achieve the intent.

    Returns:
        str: Status message.
    """
    col = _get_collection()
    if col is None:
        msg = "[MEMORY] ChromaDB not installed — skipping."
        _LOG.warning(msg)
        return msg
    try:
        doc_id = str(uuid.uuid4())          # Fixed: was os.times().elapsed
        doc    = f"Intent: {intent}\nActions: {json.dumps(actions)}"
        col.add(
            ids=[doc_id],
            documents=[doc],
            metadatas=[{
                "intent":    intent[:200],
                "timestamp": int(time.time()),
                "actions":   json.dumps(actions),
            }]
        )
        msg = f"[MEMORY] Episode stored: {doc_id[:8]}"
        _LOG.info(msg)
        return msg
    except Exception as e:
        msg = f"[MEMORY ERROR] {e}"
        _LOG.error(msg)
        return msg


def retrieve_past_task(intent: str, n_results: int = 3) -> str:
    """Query vector DB for similar past tasks.

    Args:
        intent: The task intent to search for.
        n_results: Maximum number of results to return (default 3).

    Returns:
        str: Formatted string of similar past tasks or status message.
    """
    col = _get_collection()
    if col is None:
        msg = "No similar episodes found (ChromaDB unavailable)."
        _LOG.debug(msg)
        return msg
    try:
        count = col.count()
        if count == 0:
            msg = "No episodes in memory yet."
            _LOG.debug(msg)
            return msg

        results = col.query(
            query_texts=[intent],
            n_results=min(n_results, count)
        )
        docs      = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        if not docs:
            msg = "No similar episodes found."
            _LOG.debug(msg)
            return msg

        # Only return highly similar (cosine distance < 0.4)
        relevant = [
            (d, m, dist)
            for d, m, dist in zip(docs, metadatas, distances)
            if dist < 0.4
        ]
        if not relevant:
            msg = "No similar episodes found."
            _LOG.debug(msg)
            return msg

        lines = ["📼 *Similar past tasks:*"]
        for doc, meta, dist in relevant:
            intent_prev = meta.get("intent", "?")[:80]
            actions     = json.loads(meta.get("actions", "[]"))
            ts          = time.strftime("%Y-%m-%d", time.localtime(meta.get("timestamp", 0)))
            lines.append(
                f"• [{ts}] {intent_prev}\n"
                f"  Actions: {', '.join(str(a) for a in actions[:5])}"
                f" (similarity: {1-dist:.0%})"
            )
        result = "\n".join(lines)
        _LOG.debug("Retrieved %d similar past tasks for intent: %s", len(relevant), intent)
        return result
    except Exception as e:
        msg = f"No similar episodes found. ({e})"
        _LOG.error(msg)
        return msg


def search_memory(query: str) -> List[Dict[str, Any]]:
    """Return raw list of similar episodes for programmatic use.

    Args:
        query: Search query string.

    Returns:
        List of dictionaries containing document, metadata, and distance.
    """
    col = _get_collection()
    if col is None or col.count() == 0:
        _LOG.debug("search_memory: ChromaDB unavailable or no episodes")
        return []
    try:
        results = col.query(query_texts=[query], n_results=5)
        docs      = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        return [
            {"doc": d, "meta": m, "distance": dist}
            for d, m, dist in zip(docs, metadatas, distances)
        ]
    except Exception as e:
        _LOG.error("search_memory failed: %s", e)
        return []


def clear_memory() -> str:
    """Wipe all episodes. Use with care.

    Returns:
        str: Status message.
    """
    col = _get_collection()
    if col is None:
        msg = "[MEMORY] ChromaDB not available."
        _LOG.warning(msg)
        return msg
    try:
        ids = col.get()["ids"]
        if ids:
            col.delete(ids=ids)
        msg = f"[MEMORY] Cleared {len(ids)} episodes."
        _LOG.info(msg)
        return msg
    except Exception as e:
        msg = f"[MEMORY ERROR] {e}"
        _LOG.error(msg)
        return msg


# Define public API
__all__: List[str] = [
    "store_successful_task",
    "retrieve_past_task",
    "search_memory",
    "clear_memory",
]