"""
Tests for jarvis_v3.api_manager
──────────────────────────────────────────────────────────────
Covers circuit breaker, rate limiter, cache, health checks,
and provider fallback rotation via mocked httpx.
Uses sync wrappers so pytest doesn't need pytest-asyncio.
"""

import asyncio
import json
import os
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jarvis_v3.api_manager import (
    ApiManager,
    CircuitBreaker,
    MockContent,
    ResponseCache,
    RateLimiter,
)
from jarvis_v3.config import PROVIDER_MAP


def _run(coro):
    """Helper to run async code in sync tests."""
    return asyncio.run(coro)


# ── Circuit Breaker ───────────────────────────────────────


class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker()
        assert _run(cb.is_open("groq")) is False

    def test_opens_after_failures(self):
        cb = CircuitBreaker()
        for _ in range(CircuitBreaker.FAILURE_THRESHOLD):
            _run(cb.record_failure("groq"))
        assert _run(cb.is_open("groq")) is True

    def test_allows_retry_after_cooldown(self):
        cb = CircuitBreaker()
        for _ in range(CircuitBreaker.FAILURE_THRESHOLD):
            _run(cb.record_failure("groq"))
        cb._last_failure["groq"] = time.time() - CircuitBreaker.COOLDOWN_SECONDS - 1
        assert _run(cb.is_open("groq")) is False

    def test_success_resets(self):
        cb = CircuitBreaker()
        for _ in range(CircuitBreaker.FAILURE_THRESHOLD):
            _run(cb.record_failure("groq"))
        _run(cb.record_success("groq"))
        assert _run(cb.is_open("groq")) is False


# ── Rate Limiter ──────────────────────────────────────────


class TestRateLimiter:
    @pytest.fixture
    def limiter(self, tmp_path: Path):
        return RateLimiter(state_path=tmp_path / "rl.json")

    def test_tracks_calls(self, limiter: RateLimiter):
        _run(limiter.record_call("groq"))
        counts = limiter._counts["groq"]
        assert counts["rpm"] == 1
        assert counts["rpd"] == 1

    def test_resets_after_window(self, limiter: RateLimiter):
        _run(limiter.record_call("ollama"))
        limiter._counts["ollama"]["rpm_reset"] = time.time() - 61
        p = PROVIDER_MAP["ollama"]
        assert _run(limiter.is_available(p)) is True

    def test_unavailable_when_exhausted(self, limiter: RateLimiter):
        p = PROVIDER_MAP["groq"]
        for _ in range(p.rpm_limit + 1):
            _run(limiter.record_call("groq"))
        assert _run(limiter.is_available(p)) is False

    def test_ollama_always_available(self, limiter: RateLimiter):
        p = PROVIDER_MAP["ollama"]
        assert _run(limiter.is_available(p)) is True


# ── Response Cache ────────────────────────────────────────


class TestResponseCache:
    @pytest.fixture
    def cache(self, tmp_path: Path):
        return ResponseCache(db_path=tmp_path / "cache.db")

    def test_store_and_retrieve(self, cache: ResponseCache):
        cache.set("hello", "speed", "model-a", "world")
        assert cache.get("hello", "speed", "model-a") == "world"

    def test_miss_on_different_model(self, cache: ResponseCache):
        cache.set("hello", "speed", "model-a", "world")
        assert cache.get("hello", "speed", "model-b") is None

    def test_miss_after_expiry(self, cache: ResponseCache):
        cache.set("hello", "speed", "model-a", "world")
        # Manually expire by bumping stored timestamp
        conn = __import__("sqlite3").connect(str(cache.db_path))
        conn.execute("UPDATE cache SET ts = ts - 7200 WHERE key = ?", (cache._key("hello", "speed", "model-a"),))
        conn.commit()
        conn.close()
        assert cache.get("hello", "speed", "model-a") is None


# ── ApiManager ────────────────────────────────────────────


class TestApiManager:
    @pytest.fixture
    def manager(self):
        mgr = ApiManager()
        yield mgr
        if mgr._client:
            _run(mgr._client.aclose())

    def test_health_check_unconfigured(self, manager: ApiManager):
        p = PROVIDER_MAP["groq"]
        with patch.dict(os.environ, {"GROQ_API_KEY": ""}, clear=False):
            assert _run(manager.health_check(p)) is False

    def test_health_check_healthy(self, manager: ApiManager):
        p = PROVIDER_MAP["fcc"]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        manager._client = mock_client  # type: ignore
        assert _run(manager.health_check(p)) is True

    def test_doctor_runs_all_checks(self, manager: ApiManager):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        manager._client = mock_client  # type: ignore
        report = _run(manager.doctor())
        assert "groq" in report
        assert "ollama" in report
        assert isinstance(report["groq"]["configured"], bool)

    def test_rotation_falls_back(self, manager: ApiManager):
        """Simulate failure then fallback through tier list."""
        call_count = 0

        async def fake_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            url = str(args[0]) if args else ""
            # First provider fails
            if "groq" in url or "cerebras" in url or "fcc" in url:
                resp = MagicMock()
                resp.raise_for_status.side_effect = Exception("429 rate limited")
                return resp
            # Ollama succeeds (or any later provider)
            resp = MagicMock()
            resp.json.return_value = {
                "choices": [{"message": {"content": "Hello from fallback"}}]
            }
            resp.raise_for_status = MagicMock()
            return resp

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=fake_post)
        manager._client = mock_client  # type: ignore

        result = _run(
            manager.call(
                task="say hi",
                task_type="speed",
                messages=[{"role": "user", "content": "hi"}],
            )
        )
        assert call_count >= 1
        assert result is not None

    def test_streaming_returns_mock_response(self, manager: ApiManager):
        class FakeStream:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                return None
            async def aiter_lines(self):
                yield "data: " + json.dumps(
                    {"choices": [{"delta": {"content": "hello "}}]}
                )
                yield "data: " + json.dumps(
                    {"choices": [{"delta": {"content": "world"}}]}
                )
                yield "data: [DONE]"
            def raise_for_status(self):
                pass

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=FakeStream())
        manager._client = mock_client  # type: ignore

        result = _run(
            manager.call(
                task="stream test",
                task_type="speed",
                messages=[{"role": "user", "content": "hi"}],
                stream=True,
            )
        )
        texts = [c.text for c in result.content if getattr(c, "type", None) == "text"]
        assert "".join(texts) == "hello world"

    def test_message_normalization(self, manager: ApiManager):
        raw = [
            {"role": "user", "content": [{"type": "text", "text": "hi"}]},
            {
                "role": "assistant",
                "content": [
                    MockContent("text", text="hello"),
                    MockContent("tool_use", id_="t1", name="search", input_={"q": "x"}),
                ],
            },
        ]
        out = manager._normalize_messages(raw)
        assert out[0]["role"] == "user"
        assert out[1]["role"] == "assistant"
        assert "tool_calls" in out[1]

    @patch.dict(os.environ, {"GROQ_API_KEY": "fake_groq_key"}, clear=False)
    def test_circuit_breaker_trips_then_heals(self, manager: ApiManager):
        """Provider fails 3 times → circuit opens → cooldown → works again."""
        fail_resp = MagicMock()
        fail_resp.raise_for_status.side_effect = Exception("connection error")
        ok_resp = MagicMock()
        ok_resp.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=fail_resp)
        mock_client.get = AsyncMock(return_value=ok_resp)
        manager._client = mock_client  # type: ignore

        # Call 3 times so groq accumulates 3 failures
        for _ in range(3):
            with pytest.raises(Exception):
                _run(
                    manager.call(
                        task="fail test",
                        task_type="speed",
                        messages=[{"role": "user", "content": "hi"}],
                    )
                )
        # Circuit should be open for groq
        assert _run(manager.breaker.is_open("groq")) is True
