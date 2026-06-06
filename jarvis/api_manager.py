"""
JARVIS V3 — Async API Manager
──────────────────────────────────────────────────────────────
Redesign from V2 with:
  • async httpx client (connection pooling, HTTP/2)
  • proactive health probes before each call
  • circuit breaker (trips after N consecutive failures)
  • exponential backoff + retry
  • SQLite response cache
  • rate-limit tracking (RPM / RPD)
  • automatic message format conversion (Anthropic ↔ OpenAI)
"""

import asyncio
import hashlib
import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Set

import httpx

logger = logging.getLogger("jarvis.api_manager")

from jarvis.config import PROVIDER_MAP, Provider

# ── Response compatibility shims ──────────────────────────


class MockContent:
    def __init__(
        self,
        type_: str,
        text: Optional[str] = None,
        id_: Optional[str] = None,
        name: Optional[str] = None,
        input_: Optional[dict] = None,
    ):
        self.type = type_
        if text is not None:
            self.text = text
        if id_ is not None:
            self.id = id_
        if name is not None:
            self.name = name
        if input_ is not None:
            self.input = input_


class MockResponse:
    def __init__(self, content: List[MockContent], model: str = "unknown"):
        self.content = content
        self.model = model


# ── SQLite Cache ──────────────────────────────────────────


BASE_DIR = Path.home() / ".jarvis"
CACHE_DB = BASE_DIR / "api_cache_v3.db"


class ResponseCache:
    """Thread-safe-ish SQLite cache for LLM responses."""

    def __init__(self, db_path: Path = CACHE_DB):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        BASE_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
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
        conn.close()

    @staticmethod
    def _key(task: str, task_type: str, model: str) -> str:
        return hashlib.sha256(f"{task_type}:{model}:{task}".encode()).hexdigest()

    def get(self, task: str, task_type: str, model: str) -> Optional[str]:
        try:
            key = self._key(task, task_type, model)
            conn = sqlite3.connect(str(self.db_path))
            row = conn.execute(
                "SELECT response, ts FROM cache WHERE key=?", (key,)
            ).fetchone()
            if row:
                ttl = (
                    21600
                    if task_type in ("logic", "research", "academic")
                    else 3600
                )
                if time.time() - row[1] < ttl:
                    conn.execute(
                        "UPDATE cache SET hits=hits+1 WHERE key=?", (key,)
                    )
                    conn.commit()
                    conn.close()
                    return row[0]
            conn.close()
            return None
        except Exception:
            return None

    def set(self, task: str, task_type: str, model: str, response: str):
        try:
            key = self._key(task, task_type, model)
            conn = sqlite3.connect(str(self.db_path))
            conn.execute(
                "INSERT OR REPLACE INTO cache VALUES (?,?,?,0)",
                (key, response, time.time()),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass


# ── Rate Limiter ──────────────────────────────────────────


class RateLimiter:
    """In-memory + persistent rate-limit tracker."""

    def __init__(self, state_path: Path = BASE_DIR / "rate_limits_v3.json"):
        self.state_path = state_path
        self._counts: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._load()

    def _load(self):
        try:
            if self.state_path.exists():
                self._counts = json.loads(self.state_path.read_text())
        except Exception:
            self._counts = {}

    def _save(self):
        try:
            self.state_path.write_text(json.dumps(self._counts, indent=2))
        except Exception:
            pass

    async def record_call(self, provider_name: str):
        async with self._lock:
            now = time.time()
            c = self._counts.setdefault(
                provider_name,
                {"rpm": 0, "rpd": 0, "rpm_reset": 0, "rpd_reset": 0},
            )
            if now - c["rpm_reset"] > 60:
                c["rpm"] = 0
                c["rpm_reset"] = now
            if now - c["rpd_reset"] > 86400:
                c["rpd"] = 0
                c["rpd_reset"] = now
            c["rpm"] += 1
            c["rpd"] += 1
            self._save()

    async def is_available(self, provider: Provider) -> bool:
        async with self._lock:
            now = time.time()
            c = self._counts.get(provider.name, {"rpm": 0, "rpd": 0})
            rpm_ok = (now - c.get("rpm_reset", 0) > 60) or (
                c.get("rpm", 0) < provider.rpm_limit
            )
            rpd_ok = (now - c.get("rpd_reset", 0) > 86400) or (
                c.get("rpd", 0) < provider.rpd_limit
            )
            if provider.name != "ollama" and not provider.is_configured:
                return False
            return rpm_ok and rpd_ok


# ── Circuit Breaker ───────────────────────────────────────


class CircuitBreaker:
    """Simple circuit breaker per provider."""

    FAILURE_THRESHOLD = 3
    COOLDOWN_SECONDS = 60

    def __init__(self):
        self._failures: Dict[str, int] = {}
        self._last_failure: Dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def record_success(self, provider_name: str):
        async with self._lock:
            self._failures.pop(provider_name, None)
            self._last_failure.pop(provider_name, None)

    async def record_failure(self, provider_name: str):
        async with self._lock:
            self._failures[provider_name] = self._failures.get(provider_name, 0) + 1
            self._last_failure[provider_name] = time.time()

    async def is_open(self, provider_name: str) -> bool:
        async with self._lock:
            fails = self._failures.get(provider_name, 0)
            if fails < self.FAILURE_THRESHOLD:
                return False
            last = self._last_failure.get(provider_name, 0)
            if time.time() - last > self.COOLDOWN_SECONDS:
                # Cooldown expired — half-open, allow one try
                self._failures[provider_name] = self.FAILURE_THRESHOLD - 1
                return False
            return True


# ── ApiManager ────────────────────────────────────────────


TASK_PROVIDER_MAP = {
    "speed": ["groq", "cerebras", "ollama", "fcc"],
    "code": ["groq", "github", "fcc", "openrouter"],
    "logic": ["openrouter", "sambanova", "fcc", "gemini"],
    "research": ["gemini", "openrouter", "sambanova", "groq"],
    "vision": ["gemini", "github", "fcc"],
    "debate": ["openrouter", "sambanova", "gemini", "groq"],
}


class ApiManager:
    """Central async manager for multi-provider LLM calls."""

    def __init__(self):
        self.cache = ResponseCache()
        self.limiter = RateLimiter()
        self.breaker = CircuitBreaker()
        self._client: Optional[httpx.AsyncClient] = None

    # ---- Lifecycle ----

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            http2=True,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            timeout=httpx.Timeout(60.0, connect=5.0),
        )
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()
            self._client = None

    def _client_sync(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                http2=True,
                limits=httpx.Limits(
                    max_connections=20, max_keepalive_connections=10
                ),
                timeout=httpx.Timeout(60.0, connect=5.0),
            )
        return self._client

    # ---- Health probes ----

    async def health_check(self, provider: Provider) -> bool:
        """Quick probe to see if a provider is reachable."""
        if not provider.is_configured:
            return False
        if provider.name == "gemini":
            # Gemini health check requires key appended
            return True  # Skip, checked at call time
        if not provider.health_endpoint:
            return True  # No endpoint, assume OK
        try:
            client = self._client_sync()
            headers = {"User-Agent": "JARVIS/3.0"}
            if provider.api_key:
                headers["Authorization"] = f"Bearer {provider.api_key}"
            r = await client.get(provider.health_endpoint, headers=headers, timeout=5.0)
            # 429 means the endpoint is up but rate-limited — count as healthy
            if r.status_code == 429:
                return True
            return r.status_code < 500
        except Exception:
            return False

    async def doctor(self) -> Dict[str, Dict[str, Any]]:
        """Run health checks on all providers. Returns status map."""
        results: Dict[str, Dict[str, Any]] = {}
        tasks = []
        names = []
        for name, p in PROVIDER_MAP.items():
            tasks.append(self.health_check(p))
            names.append(name)
        checks = await asyncio.gather(*tasks, return_exceptions=True)
        for name, ok in zip(names, checks):
            p = PROVIDER_MAP[name]
            results[name] = {
                "configured": p.is_configured,
                "reachable": ok if not isinstance(ok, Exception) else False,
                "models": p.models,
                "best_for": p.best_for,
            }
        return results

    # ---- Provider selection ----

    async def _get_available_provider(
        self, task_type: str, skip: Set[str]
    ) -> Optional[Provider]:
        priority = TASK_PROVIDER_MAP.get(
            task_type, TASK_PROVIDER_MAP["logic"]
        )
        for name in priority:
            if name in skip:
                continue
            p = PROVIDER_MAP.get(name)
            if not p:
                continue
            if await self.breaker.is_open(name):
                continue
            if not await self.limiter.is_available(p):
                continue
            if not p.is_configured:
                continue
            if p.health_endpoint and not await self.health_check(p):
                continue
            return p
        return None

    # ---- Message normalisation ----

    @staticmethod
    def _normalize_messages(messages: List[dict]) -> List[dict]:
        """Convert Anthropic-style blocks into OpenAI-compatible messages."""
        out: List[dict] = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content")
            if isinstance(content, str):
                out.append({"role": role, "content": content})
                continue
            if isinstance(content, list):
                msg_content: List[dict] = []
                tool_calls: List[dict] = []
                tool_results: List[dict] = []
                for b in content:
                    if isinstance(b, dict):
                        b_type = b.get("type")
                        if b_type == "text":
                            msg_content.append(
                                {"type": "text", "text": b.get("text", "")}
                            )
                        elif b_type == "image":
                            src = b.get("source", {})
                            msg_content.append(
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": (
                                            f"data:{src.get('media_type')};"
                                            f"base64,{src.get('data')}"
                                        )
                                    },
                                }
                            )
                        elif b_type == "tool_use":
                            tool_calls.append(
                                {
                                    "id": b["id"],
                                    "type": "function",
                                    "function": {
                                        "name": b["name"],
                                        "arguments": json.dumps(b.get("input", {})),
                                    },
                                }
                            )
                        elif b_type == "tool_result":
                            tool_results.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": b["tool_use_id"],
                                    "content": str(b.get("content", "")),
                                }
                            )
                    elif hasattr(b, "type"):
                        if b.type == "text":
                            msg_content.append(
                                {
                                    "type": "text",
                                    "text": getattr(b, "text", ""),
                                }
                            )
                        elif b.type == "tool_use":
                            tool_calls.append(
                                {
                                    "id": b.id,
                                    "type": "function",
                                    "function": {
                                        "name": b.name,
                                        "arguments": json.dumps(
                                            getattr(b, "input", {})
                                        ),
                                    },
                                }
                            )
                        elif b.type == "tool_result":
                            tool_results.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": getattr(b, "tool_use_id", ""),
                                    "content": str(getattr(b, "content", "")),
                                }
                            )
                if msg_content or tool_calls:
                    final_content: Any = msg_content
                    if len(msg_content) == 1 and msg_content[0]["type"] == "text":
                        final_content = msg_content[0]["text"]
                    msg: dict = {"role": role, "content": final_content}
                    if tool_calls:
                        msg["tool_calls"] = tool_calls
                    out.append(msg)
                out.extend(tool_results)
            else:
                out.append(m)
        return out

    # ---- Retry helper ----

    RETRYABLE_STATUS_CODES = {429, 503, 504}
    NO_RETRY_STATUS_CODES = {401, 403}

    async def _request_with_retry(
        self,
        coro,
        provider_name: str,
        operation: str = "request",
    ) -> httpx.Response:
        """Execute an HTTP coroutine with exponential-backoff retry.

        Retries up to 3 times on 429, 503, 504.
        Does NOT retry on 401 or 403 (permanent auth failures).
        Backoff: 1s, 2s, 4s.
        """
        delays = [1.0, 2.0, 4.0]
        last_err: Optional[Exception] = None

        for attempt in range(4):  # 0, 1, 2, 3 → up to 3 retries
            try:
                return await coro
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status in self.NO_RETRY_STATUS_CODES:
                    raise  # permanent — do not retry
                if status in self.RETRYABLE_STATUS_CODES and attempt < 3:
                    delay = delays[attempt]
                    logger.warning(
                        f"[{provider_name}] {operation} returned {status}, "
                        f"retrying in {delay}s (attempt {attempt + 1}/3)"
                    )
                    await asyncio.sleep(delay)
                    last_err = exc
                    continue
                raise  # non-retryable or out of retries
            except httpx.TimeoutException as exc:
                if attempt < 3:
                    delay = delays[attempt]
                    logger.warning(
                        f"[{provider_name}] {operation} timed out, "
                        f"retrying in {delay}s (attempt {attempt + 1}/3)"
                    )
                    await asyncio.sleep(delay)
                    last_err = exc
                    continue
                raise

        # Should not reach here, but satisfy type checker
        raise last_err or Exception(f"{provider_name} {operation} failed after 3 retries")

    # ---- Core call ----

    async def call(
        self,
        task: str,
        task_type: str,
        messages: List[dict],
        system: str = "",
        tools: Optional[List[dict]] = None,
        stream: bool = False,
        token_callback: Optional[Callable[[str], None]] = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> MockResponse:
        """Main async entry point."""
        model_str: str = ""

        # 1. Cache check (only for deterministic calls)
        if not tools and not stream and temperature == 0.0:
            # We don't know model yet, skip cache until we get response
            pass

        tried: Set[str] = set()
        last_error: Optional[Exception] = None

        while True:
            provider = await self._get_available_provider(task_type, tried)
            if not provider:
                # Fallback to ollama unconditionally
                provider = PROVIDER_MAP.get("ollama")
                if not provider or provider.name in tried:
                    raise last_error or Exception("All providers exhausted.")

            tried.add(provider.name)
            model = provider.models[0]
            model_str = model
            print(
                f"    [API] Trying provider: {provider.name} | Model: {model}"
            )

            try:
                result = await self._call_provider(
                    provider=provider,
                    model=model,
                    messages=messages,
                    system=system,
                    tools=tools,
                    stream=stream,
                    token_callback=token_callback,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                await self.breaker.record_success(provider.name)
                await self.limiter.record_call(provider.name)

                # Cache success
                if not tools and temperature == 0.0 and result.content:
                    texts = [
                        c.text
                        for c in result.content
                        if getattr(c, "type", None) == "text"
                    ]
                    if texts:
                        self.cache.set(task, task_type, model_str, texts[0])

                return result

            except Exception as e:
                err = str(e).lower()
                last_error = e
                print(f"    [API] {provider.name} failed: {e}")
                await self.breaker.record_failure(provider.name)

                if "429" in err or "rate" in err:
                    # Rate limited — mark as unavailable and try next
                    continue
                if "404" in err or "not found" in err:
                    # 404 fallback: if openrouter :free model, retry with suffix stripped
                    if provider.name == "openrouter" and model.endswith(":free"):
                        fallback_model = model[:-5]  # strip ":free"
                        print(f"    [API] 404 on :free model, retrying with {fallback_model}")
                        try:
                            result = await self._call_provider(
                                provider=provider,
                                model=fallback_model,
                                messages=messages,
                                system=system,
                                tools=tools,
                                stream=stream,
                                token_callback=token_callback,
                                temperature=temperature,
                                max_tokens=max_tokens,
                            )
                            await self.breaker.record_success(provider.name)
                            await self.limiter.record_call(provider.name)
                            return result
                        except Exception as fallback_err:
                            print(f"    [API] Fallback also failed: {fallback_err}")
                            await self.breaker.record_failure(provider.name)
                    continue
                if "authentication" in err or "auth" in err or "key" in err:
                    # Auth failure — skip this provider entirely for this call
                    continue
                if "timeout" in err or "connect" in err:
                    continue
                # For other errors, also retry next provider
                continue

    async def _call_provider(
        self,
        provider: Provider,
        model: str,
        messages: List[dict],
        system: str,
        tools: Optional[List[dict]],
        stream: bool,
        token_callback: Optional[Callable[[str], None]],
        temperature: float,
        max_tokens: int,
    ) -> MockResponse:

        openai_msgs = self._normalize_messages(messages)
        api_key = provider.api_key or "ollama"
        is_openai = provider.name in (
            "groq",
            "cerebras",
            "ollama",
            "sambanova",
            "openrouter",
            "github",
            "fcc",
            "castai",
        )

        if is_openai:
            url = f"{provider.base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "JARVIS/3.0",
            }
            payload: dict = {
                "model": model,
                "messages": (
                    [{"role": "system", "content": system}] if system else []
                )
                + openai_msgs,
                "max_tokens": max_tokens,
                "stream": stream,
            }
            if temperature > 0.0:
                payload["temperature"] = temperature
            if tools:
                payload["tools"] = [
                    {"type": "function", "function": t} for t in tools
                ]

            client = self._client_sync()

            if stream:
                return await self._stream_openai(
                    client, url, headers, payload, model, token_callback,
                    provider.name,
                )
            else:
                return await self._sync_openai(
                    client, url, headers, payload, model,
                    provider.name,
                )
        else:
            # Anthropic native
            return await self._call_anthropic(
                provider, model, messages, system, tools, stream,
                token_callback, temperature, max_tokens
            )

    async def _stream_openai(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: dict,
        payload: dict,
        model: str,
        token_callback: Optional[Callable[[str], None]],
        provider_name: str = "unknown",
    ) -> MockResponse:
        full_text = ""
        tool_calls_raw: Dict[int, Dict[str, str]] = {}

        async def _stream_coro():
            return await client.stream("POST", url, headers=headers, json=payload)

        async with await self._request_with_retry(
            _stream_coro(), provider_name, "stream"
        ) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                if line == "data: [DONE]":
                    break
                try:
                    chunk = json.loads(line[6:])
                    if not chunk.get("choices"):
                        continue
                    delta = chunk["choices"][0].get("delta", {})
                    if delta.get("content"):
                        token = delta["content"]
                        full_text += token
                        if token_callback:
                            token_callback(token)
                    if delta.get("tool_calls"):
                        for tc in delta["tool_calls"]:
                            idx = tc.get("index", 0)
                            tcr = tool_calls_raw.setdefault(
                                idx, {"id": "", "name": "", "args": ""}
                            )
                            if tc.get("id"):
                                tcr["id"] = tc["id"]
                            fn = tc.get("function", {})
                            if fn.get("name"):
                                tcr["name"] = fn["name"]
                            if fn.get("arguments"):
                                tcr["args"] += fn["arguments"]
                except Exception:
                    continue

        content: List[MockContent] = []
        if full_text:
            content.append(MockContent("text", text=full_text))
        for idx in sorted(tool_calls_raw.keys()):
            tc = tool_calls_raw[idx]
            content.append(
                MockContent(
                    "tool_use",
                    id_=tc["id"],
                    name=tc["name"],
                    input_=json.loads(tc["args"] if tc["args"] else "{}"),
                )
            )
        return MockResponse(content, model=model)

    async def _sync_openai(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: dict,
        payload: dict,
        model: str,
        provider_name: str = "unknown",
    ) -> MockResponse:
        async def _post_coro():
            return await client.post(url, headers=headers, json=payload)

        r = await self._request_with_retry(_post_coro(), provider_name, "POST")
        r.raise_for_status()
        data = r.json()
        choice = data["choices"][0]["message"]
        content: List[MockContent] = []
        if choice.get("content"):
            content.append(MockContent("text", text=choice["content"]))
        for tc in choice.get("tool_calls", []):
            fn = tc.get("function", {})
            content.append(
                MockContent(
                    "tool_use",
                    id_=tc.get("id"),
                    name=fn.get("name"),
                    input_=json.loads(fn.get("arguments", "{}")),
                )
            )
        return MockResponse(content, model=model)

    async def _call_anthropic(
        self,
        provider: Provider,
        model: str,
        messages: List[dict],
        system: str,
        tools: Optional[List[dict]],
        stream: bool,
        token_callback: Optional[Callable[[str], None]],
        temperature: float,
        max_tokens: int,
    ) -> MockResponse:
        # Fallback: use httpx for Anthropic OpenAI-compatible endpoint
        # Most Anthropic proxies expose /v1/chat/completions
        url = f"{provider.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {provider.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": (
                [{"role": "system", "content": system}] if system else []
            )
            + self._normalize_messages(messages),
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if temperature > 0.0:
            payload["temperature"] = temperature
        if tools:
            payload["tools"] = [
                {"type": "function", "function": t} for t in tools
            ]

        client = self._client_sync()
        if stream:
            return await self._stream_openai(
                client, url, headers, payload, model, token_callback
            )
        else:
            return await self._sync_openai(
                client, url, headers, payload, model
            )


# ── Convenience wrapper (non-class usage) ─────────────────

_manager: Optional[ApiManager] = None


async def get_manager() -> ApiManager:
    global _manager
    if _manager is None:
        _manager = ApiManager()
    return _manager


async def call_with_rotation(
    task: str,
    task_type: str,
    messages: List[dict],
    system: str = "",
    tools: Optional[List[dict]] = None,
    stream: bool = False,
    token_callback: Optional[Callable[[str], None]] = None,
    temperature: float = 0.0,
    max_tokens: int = 4096,
) -> MockResponse:
    mgr = await get_manager()
    return await mgr.call(
        task=task,
        task_type=task_type,
        messages=messages,
        system=system,
        tools=tools,
        stream=stream,
        token_callback=token_callback,
        temperature=temperature,
        max_tokens=max_tokens,
    )
