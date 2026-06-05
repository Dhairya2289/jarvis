"""JARVIS API Rotation Manager — Redundancy & Quota Tracking

Tracks rate limits per provider in real-time, auto-rotates when quotas are
exhausted, and caches common responses.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Literal, TypedDict

import anthropic
import httpx

from config import BASE_DIR

_log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
#  Paths
# ═══════════════════════════════════════════════════════════
CACHE_DB: Final[Path] = BASE_DIR / "api_cache.db"
LIMITS_FILE: Final[Path] = BASE_DIR / "rate_limits.json"


# ═══════════════════════════════════════════════════════════
#  Typed data structures
# ═══════════════════════════════════════════════════════════
class _ProviderDict(TypedDict):
    rpm: int
    rpd: int
    rpm_reset: float
    rpd_reset: float


@dataclass(frozen=True, slots=True)
class Provider:
    """An LLM API provider with routing metadata."""
    name: str
    base_url: str
    api_key_env: str
    models: tuple[str, ...]
    rpm_limit: int
    rpd_limit: int
    best_for: tuple[str, ...]


# ═══════════════════════════════════════════════════════════
#  Provider registry
# ═══════════════════════════════════════════════════════════
PROVIDERS: Final[tuple[Provider, ...]] = (
    Provider(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY",
        models=("llama-3.3-70b-versatile", "llama-3.1-8b-instant"),
        rpm_limit=30,
        rpd_limit=14400,
        best_for=("speed", "code"),
    ),
    Provider(
        name="cerebras",
        base_url="https://api.cerebras.ai/v1",
        api_key_env="CEREBRAS_API_KEY",
        models=("llama-3.3-70b", "llama3.1-8b"),
        rpm_limit=30,
        rpd_limit=25000,
        best_for=("speed",),
    ),
    Provider(
        name="gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        api_key_env="GEMINI_API_KEY",
        models=("gemini-2.0-flash", "gemini-2.0-flash-lite"),
        rpm_limit=15,
        rpd_limit=1500,
        best_for=("vision", "research"),
    ),
    Provider(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        models=("deepseek/deepseek-r1:free", "deepseek/deepseek-v3:free"),
        rpm_limit=20,
        rpd_limit=1000,
        best_for=("logic", "debate", "research"),
    ),
    Provider(
        name="sambanova",
        base_url="https://api.sambanova.ai/v1",
        api_key_env="SAMBANOVA_API_KEY",
        models=("Meta-Llama-3.3-70B-Instruct", "Meta-Llama-3.1-405B-Instruct"),
        rpm_limit=30,
        rpd_limit=10000,
        best_for=("logic", "research"),
    ),
    Provider(
        name="github",
        base_url="https://models.inference.ai.azure.com",
        api_key_env="GITHUB_TOKEN",
        models=("gpt-4o", "Meta-Llama-3.1-70B-Instruct"),
        rpm_limit=10,
        rpd_limit=150,
        best_for=("code", "logic"),
    ),
    Provider(
        name="fcc",
        base_url="http://127.0.0.1:8082",
        api_key_env="FCC_AUTH_TOKEN",
        models=("claude-3-5-sonnet-20241022",),
        rpm_limit=20,
        rpd_limit=500,
        best_for=("logic", "code"),
    ),
    Provider(
        name="ollama",
        base_url="http://localhost:11434/v1",
        api_key_env="",
        models=("qwen2.5:3b", "phi4-mini"),
        rpm_limit=999,
        rpd_limit=999999,
        best_for=("speed", "local"),
    ),
)

PROVIDER_MAP: Final[dict[str, Provider]] = {p.name: p for p in PROVIDERS}

# ═══════════════════════════════════════════════════════════
#  Response shims (backward-compatible)
# ═══════════════════════════════════════════════════════════
class MockContent:
    def __init__(
        self,
        type: str,  # noqa: A002  — matches original field name
        text: str | None = None,
        id: str | None = None,  # noqa: A002
        name: str | None = None,
        input: dict | None = None,  # noqa: A002
    ):
        self.type = type
        if text is not None:
            self.text = text
        if id is not None:
            self.id = id
        if name is not None:
            self.name = name
        if input is not None:
            self.input = input


class MockResponse:
    def __init__(self, content: list[MockContent], model: str = "unknown"):
        self.content = content
        self.model = model


# ═══════════════════════════════════════════════════════════
#  Rate-limit tracker
# ═══════════════════════════════════════════════════════════
class RateLimitTracker:
    """Per-provider RPM / RPD tracker with persistent JSON backing."""

    def __init__(self) -> None:
        self._counts: defaultdict[str, _ProviderDict] = defaultdict(
            lambda: _ProviderDict(rpm=0, rpd=0, rpm_reset=0.0, rpd_reset=0.0)
        )
        self._load()

    def _load(self) -> None:
        if not LIMITS_FILE.exists():
            return
        try:
            data = json.loads(LIMITS_FILE.read_text(encoding="utf-8"))
            for name, entry in data.items():
                self._counts[name] = _ProviderDict(
                    rpm=int(entry.get("rpm", 0)),
                    rpd=int(entry.get("rpd", 0)),
                    rpm_reset=float(entry.get("rpm_reset", 0)),
                    rpd_reset=float(entry.get("rpd_reset", 0)),
                )
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            _log.warning("Corrupt rate-limit file %s: %s", LIMITS_FILE, exc)

    def _save(self) -> None:
        try:
            LIMITS_FILE.write_text(
                json.dumps(dict(self._counts), indent=2), encoding="utf-8"
            )
        except OSError as exc:
            _log.warning("Could not save rate limits: %s", exc)

    def record_call(self, provider_name: str) -> None:
        now = time.time()
        c = self._counts[provider_name]
        if now - c["rpm_reset"] > 60:
            c["rpm"] = 0
            c["rpm_reset"] = now
        if now - c["rpd_reset"] > 86400:
            c["rpd"] = 0
            c["rpd_reset"] = now
        c["rpm"] += 1
        c["rpd"] += 1
        self._save()

    def is_available(self, provider: Provider) -> bool:
        now = time.time()
        c = self._counts[provider.name]
        rpm_ok = (now - c["rpm_reset"] > 60) or (c["rpm"] < provider.rpm_limit)
        rpd_ok = (now - c["rpd_reset"] > 86400) or (c["rpd"] < provider.rpd_limit)
        if provider.name != "ollama" and not os.environ.get(provider.api_key_env):
            return False
        return rpm_ok and rpd_ok

    def mark_exhausted(self, provider_name: str) -> None:
        """Force a provider to appear exhausted (e.g. after a 429)."""
        self._counts[provider.name]["rpm"] = PROVIDER_MAP[provider_name].rpm_limit
        self._save()


# Global singleton — safe because defaultdict is thread-safe for reads/updates
_tracker: RateLimitTracker | None = None


def _get_tracker() -> RateLimitTracker:
    global _tracker
    if _tracker is None:
        _tracker = RateLimitTracker()
    return _tracker


# ═══════════════════════════════════════════════════════════
#  SQLite response cache
# ═══════════════════════════════════════════════════════════
def _init_cache() -> sqlite3.Connection:
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CACHE_DB))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cache (
            key TEXT PRIMARY KEY,
            response TEXT,
            ts REAL,
            hits INTEGER DEFAULT 0
        )
        """
    )
    conn.commit()
    return conn


def _cache_key(task: str, task_type: str) -> str:
    return hashlib.sha256(f"{task_type}:{task}".encode()).hexdigest()


def cache_get(task: str, task_type: str) -> str | None:
    try:
        key = _cache_key(task, task_type)
        conn = _init_cache()
        row = conn.execute(
            "SELECT response, ts FROM cache WHERE key=?", (key,)
        ).fetchone()
        if not row:
            return None
        ttl = 21600 if task_type in ("logic", "research", "academic") else 3600
        if time.time() - row[1] > ttl:
            return None
        conn.execute("UPDATE cache SET hits=hits+1 WHERE key=?", (key,))
        conn.commit()
        return row[0]
    except sqlite3.Error as exc:
        _log.debug("Cache read error: %s", exc)
        return None


def cache_set(task: str, task_type: str, response: str) -> None:
    try:
        key = _cache_key(task, task_type)
        conn = _init_cache()
        conn.execute(
            "INSERT OR REPLACE INTO cache VALUES (?,?,?,0)",
            (key, response, time.time()),
        )
        conn.commit()
    except sqlite3.Error as exc:
        _log.debug("Cache write error: %s", exc)


# ═══════════════════════════════════════════════════════════
#  Routing map
# ═══════════════════════════════════════════════════════════
TASK_PROVIDER_MAP: Final[dict[str, tuple[str, ...]]] = {
    "speed": ("groq", "cerebras", "ollama", "fcc"),
    "code": ("groq", "github", "fcc", "openrouter"),
    "logic": ("openrouter", "sambanova", "fcc", "gemini"),
    "research": ("gemini", "openrouter", "sambanova", "groq"),
    "vision": ("gemini", "github", "fcc"),
    "debate": ("openrouter", "sambanova", "gemini", "groq"),
}


def get_best_provider(task_type: str, skip: set[str] | None = None) -> Provider | None:
    skip = skip or set()
    tracker = _get_tracker()
    priority = TASK_PROVIDER_MAP.get(task_type, TASK_PROVIDER_MAP["logic"])
    for name in priority:
        if name in skip:
            continue
        p = PROVIDER_MAP.get(name)
        if p is not None and tracker.is_available(p):
            return p
    return None


def get_model_for_provider(provider: Provider, task_type: str) -> str:
    if provider.name == "ollama" and task_type == "vision":
        return "llama3.2-vision:3b"
    return provider.models[0]


# ═══════════════════════════════════════════════════════════
#  Health probe
# ═══════════════════════════════════════════════════════════
def health_check_provider(provider: Provider, *, timeout: float = 5.0) -> bool:
    """Send a lightweight probe to verify a provider is reachable."""
    try:
        if provider.name == "ollama":
            with httpx.Client(timeout=timeout) as client:
                r = client.get(f"{provider.base_url}/models")
                return r.status_code < 500
        api_key = os.environ.get(provider.api_key_env, "")
        with httpx.Client(timeout=timeout) as client:
            r = client.get(
                f"{provider.base_url}/models",
                headers={"Authorization": f"Bearer {api_key}"} if api_key else None,
            )
            return r.status_code < 500
    except Exception as exc:
        _log.debug("Health check failed for %s: %s", provider.name, exc)
        return False


def health_check_all() -> dict[str, bool]:
    """Return health status for every registered provider."""
    return {p.name: health_check_provider(p) for p in PROVIDERS}


# ═══════════════════════════════════════════════════════════
#  Message format utils (Anthropic ↔ OpenAI)
# ═══════════════════════════════════════════════════════════
def _is_openai_provider(name: str) -> bool:
    return name in (
        "groq", "cerebras", "ollama", "sambanova", "openrouter", "github", "fcc"
    )


def _to_openai_message(
    content: list[dict[str, Any]] | Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Convert a single message content block list to OpenAI format.

    Returns (message_parts, tool_result_messages).
    """
    msg_content: list[dict[str, Any]] = []
    tool_calls: list[dict[str, Any]] = []
    tool_result_msgs: list[dict[str, Any]] = []

    for b in content:
        try:
            if isinstance(b, dict):
                b_type = b.get("type")
                if b_type == "text":
                    msg_content.append({"type": "text", "text": b.get("text", "")})
                elif b_type == "image":
                    src = b.get("source", {})
                    msg_content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": (
                                f"data:{src.get('media_type','image/png')}"
                                f";base64,{src.get('data','')}"
                            )
                        },
                    })
                elif b_type == "tool_use":
                    tool_calls.append({
                        "id": b["id"],
                        "type": "function",
                        "function": {
                            "name": b["name"],
                            "arguments": json.dumps(b.get("input", {})),
                        },
                    })
                elif b_type == "tool_result":
                    tool_result_msgs.append({
                        "role": "tool",
                        "tool_call_id": b["tool_use_id"],
                        "content": str(b.get("content", "")),
                    })
            elif hasattr(b, "type"):
                if b.type == "text":
                    msg_content.append(
                        {"type": "text", "text": getattr(b, "text", "")}
                    )
                elif b.type == "tool_use":
                    tool_calls.append({
                        "id": b.id,
                        "type": "function",
                        "function": {
                            "name": b.name,
                            "arguments": json.dumps(getattr(b, "input", {})),
                        },
                    })
        except Exception as exc:
            _log.debug("Skipping malformed message block: %s | block=%r", exc, b)

    msg: dict[str, Any] = {}
    if msg_content or tool_calls:
        if len(msg_content) == 1 and msg_content[0].get("type") == "text":
            msg = {"role": "assistant", "content": msg_content[0]["text"]}
        else:
            msg = {"role": "assistant", "content": msg_content}
        if tool_calls:
            msg["tool_calls"] = tool_calls
    return msg, tool_result_msgs


# ═══════════════════════════════════════════════════════════
#  Main call router
# ═══════════════════════════════════════════════════════════
def call_with_rotation(
    task: str,
    task_type: str,
    messages: list[dict[str, Any]],
    *,
    system: str = "",
    tools: list[dict[str, Any]] | None = None,
    stream: bool = False,
    token_callback: Callable[[str], Any] | None = None,
    tried: set[str] | None = None,
    temperature: float = 0.0,
) -> MockResponse | Any:
    """Route a task to the best available LLM provider with automatic fallback.

    Args:
        task: The user instruction (used for cache keying).
        task_type: Routing category (speed, code, logic, research, vision, debate).
        messages: Anthropic-format conversation history.
        system: System prompt.
        tools: JSON Schema tool definitions.
        stream: Whether to stream tokens.
        token_callback: Called with each token chunk when streaming.
        tried: Set of provider names already attempted (for recursion).
        temperature: Sampling temperature (0.0 = deterministic).

    Returns:
        A ``MockResponse`` for OpenAI-compatible providers, or the raw
        Anthropic ``Message`` object for Anthropic-native providers.
    """
    tried = tried or set()
    tracker = _get_tracker()

    # 1. Cache check (only when deterministic and no tools)
    if not tools and not stream and temperature == 0.0:
        cached = cache_get(task, task_type)
        if cached:
            _log.debug("Cache hit for task_type=%s", task_type)
            return MockResponse([MockContent(type="text", text=cached)])

    # 2. Provider selection
    provider = get_best_provider(task_type, skip=tried)
    if provider is None:
        ollama = PROVIDER_MAP.get("ollama")
        if ollama is not None and ollama.name not in tried:
            provider = ollama
        else:
            raise RuntimeError("All providers exhausted.")

    tried.add(provider.name)
    model = get_model_for_provider(provider, task_type)
    _log.info("Trying provider=%s model=%s task_type=%s", provider.name, model, task_type)

    api_key = os.environ.get(provider.api_key_env, "ollama")
    is_openai = _is_openai_provider(provider.name)

    try:
        # Standardise messages
        openai_msgs: list[dict[str, Any]] = []
        for m in messages:
            role = m["role"]
            content = m["content"]
            if isinstance(content, list):
                msg, tool_results = _to_openai_message(content)
                if msg:
                    msg["role"] = role
                    openai_msgs.append(msg)
                openai_msgs.extend(tool_results)
            else:
                openai_msgs.append(m)

        if is_openai:
            return _call_openai(
                provider=provider,
                model=model,
                messages=openai_msgs,
                system=system,
                tools=tools,
                stream=stream,
                token_callback=token_callback,
                task=task,
                task_type=task_type,
            )
        else:
            return _call_anthropic(
                provider=provider,
                messages=messages,
                system=system,
                tools=tools,
                stream=stream,
                token_callback=token_callback,
                task=task,
                task_type=task_type,
            )
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in (429, 404, 500, 502, 503):
            _log.warning("Provider %s returned %d — rotating.", provider.name, status)
            tracker.mark_exhausted(provider.name)
            return call_with_rotation(
                task, task_type, messages,
                system=system, tools=tools, stream=stream,
                token_callback=token_callback, tried=tried,
                temperature=temperature,
            )
        raise
    except Exception as exc:
        _log.error("Provider %s failed: %s", provider.name, exc, exc_info=True)
        raise


# ── OpenAI-compatible call ────────────────────────────────
def _call_openai(
    *,
    provider: Provider,
    model: str,
    messages: list[dict[str, Any]],
    system: str,
    tools: list[dict[str, Any]] | None,
    stream: bool,
    token_callback: Callable[[str], Any] | None,
    task: str,
    task_type: str,
) -> MockResponse:
    api_key = os.environ.get(provider.api_key_env, "ollama")
    url = f"{provider.base_url}/chat/completions"
    headers: dict[str, str] = {"Authorization": f"Bearer {api_key}"}
    payload: dict[str, Any] = {
        "model": model,
        "messages": ([{"role": "system", "content": system}] if system else []) + messages,
        "max_tokens": 4096,
        "stream": stream,
    }
    if temperature > 0.0:
        payload["temperature"] = temperature
    if tools:
        payload["tools"] = [{"type": "function", "function": t} for t in tools]

    tracker = _get_tracker()
    tracker.record_call(provider.name)

    if stream:
        full_text = ""
        tool_calls_raw: dict[int, dict[str, str]] = defaultdict(
            lambda: {"id": "", "name": "", "args": ""}
        )
        with httpx.Client(timeout=60.0) as client:
            with client.stream("POST", url, headers=headers, json=payload) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    if line == "data: [DONE]":
                        break
                    try:
                        chunk = json.loads(line[6:])
                        choice = chunk.get("choices", [{}])[0]
                        delta = choice.get("delta", {})
                        token = delta.get("content", "")
                        if token:
                            full_text += token
                            if token_callback:
                                token_callback(token)
                        for tc in delta.get("tool_calls", []):
                            idx = tc["index"]
                            if tc.get("id"):
                                tool_calls_raw[idx]["id"] = tc["id"]
                            fn = tc.get("function", {})
                            if fn.get("name"):
                                tool_calls_raw[idx]["name"] = fn["name"]
                            if fn.get("arguments"):
                                tool_calls_raw[idx]["args"] += fn["arguments"]
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

        content: list[MockContent] = []
        if full_text:
            content.append(MockContent(type="text", text=full_text))
        for idx in sorted(tool_calls_raw.keys()):
            tc = tool_calls_raw[idx]
            content.append(
                MockContent(
                    type="tool_use",
                    id=tc["id"],
                    name=tc["name"],
                    input=json.loads(tc["args"] if tc["args"] else "{}"),
                )
            )
        if not tools and full_text:
            cache_set(task, task_type, full_text)
        return MockResponse(content, model=model)

    # Non-streaming
    with httpx.Client(timeout=60.0) as client:
        r = client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
        choice = data["choices"][0]["message"]
        content = []
        if choice.get("content"):
            content.append(MockContent(type="text", text=choice["content"]))
        for tc in choice.get("tool_calls", []):
            fn = tc.get("function", {})
            content.append(
                MockContent(
                    type="tool_use",
                    id=tc.get("id"),
                    name=fn.get("name"),
                    input=json.loads(fn.get("arguments", "{}")),
                )
            )
        if not tools and choice.get("content"):
            cache_set(task, task_type, choice["content"])
        return MockResponse(content, model=model)


# ── Anthropic-native call ─────────────────────────────────
def _call_anthropic(
    *,
    provider: Provider,
    messages: list[dict[str, Any]],
    system: str,
    tools: list[dict[str, Any]] | None,
    stream: bool,
    token_callback: Callable[[str], Any] | None,
    task: str,
    task_type: str,
) -> Any:
    api_key = os.environ.get(provider.api_key_env, "")
    client = anthropic.Anthropic(
        base_url=provider.base_url,
        api_key=api_key or "freecc",
    )
    tracker = _get_tracker()
    tracker.record_call(provider.name)

    kwargs: dict[str, Any] = {
        "model": provider.models[0],
        "max_tokens": 4096,
        "system": system,
        "messages": messages,
    }
    if temperature > 0.0:
        kwargs["temperature"] = temperature
    if tools:
        kwargs["tools"] = tools

    if stream:
        with client.messages.stream(**kwargs) as s:
            for event in s:
                if event.type == "text":
                    if token_callback:
                        token_callback(event.text)
            return s.get_final_message()

    response = client.messages.create(**kwargs)

    # Detect proxy errors masquerading as content
    if (
        response.content
        and response.content[0].type == "text"
    ):
        text = response.content[0].text.lower()
        if any(kw in text for kw in ("upstream provider", "authentication failed", "model not found")):
            tracker.mark_exhausted(provider.name)
            return call_with_rotation(
                task, task_type, messages,
                system=system, tools=tools, stream=stream,
                token_callback=token_callback, tried=set(),
            )

    if not tools and response.content and response.content[0].type == "text":
        cache_set(task, task_type, response.content[0].text)

    return response


__all__ = [
    "Provider",
    "PROVIDERS",
    "PROVIDER_MAP",
    "MockContent",
    "MockResponse",
    "RateLimitTracker",
    "get_best_provider",
    "get_model_for_provider",
    "call_with_rotation",
    "cache_get",
    "cache_set",
    "health_check_provider",
    "health_check_all",
]
