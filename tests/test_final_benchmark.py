"""Final end-to-end benchmark for JARVIS unified system.

Run: PYTHONPATH=. pytest tests/test_final_benchmark.py -v
"""
import pytest
import asyncio
from jarvis.config import PROVIDER_MAP
from jarvis.api_manager import ApiManager
from jarvis.tools import dispatch_tool


class TestFinalBenchmark:
    """Post-fix verification: all critical paths."""

    @pytest.mark.asyncio
    async def test_health_all_providers(self):
        am = ApiManager()
        checks = ["kimchi", "gemini", "openrouter", "ollama"]
        results = {}
        for name in checks:
            p = PROVIDER_MAP.get(name)
            if p:
                results[name] = await am.health_check(p)
        assert results.get("kimchi") is True, "kimchi health should pass"
        assert results.get("gemini") is True, "gemini health should pass"
        assert results.get("openrouter") is True, "openrouter health should pass"
        assert results.get("ollama") is True, "ollama health should pass"

    @pytest.mark.asyncio
    async def test_kimchi_inference(self):
        am = ApiManager()
        p = PROVIDER_MAP["kimchi"]
        r = await am._call_provider(
            provider=p, model="kimi-k2.6",
            messages=[{"role": "user", "content": "Say hi"}],
            system="", tools=None, stream=False,
            token_callback=None, temperature=0.0, max_tokens=10,
        )
        texts = [getattr(c, "text", "") for c in r.content if hasattr(c, "text")]
        assert any(texts), f"Expected non-empty response, got {r.content}"

    @pytest.mark.asyncio
    async def test_openrouter_inference(self):
        """Tests OpenRouter via call() which has :free fallback."""
        am = ApiManager()
        # Use call() not _call_provider to exercise 404 fallback
        r = await am.call(
            task="Say hi",
            task_type="logic",
            messages=[{"role": "user", "content": "Say hi"}],
            max_tokens=10,
        )
        texts = [getattr(c, "text", "") for c in r.content if hasattr(c, "text")]
        assert any(texts), f"Expected non-empty response, got {r.content}"

    def test_tool_list_apps(self):
        r = dispatch_tool("list_apps", {})
        assert not r.startswith("[ERROR]"), f"list_apps failed: {r}"
        assert "apps" in r.lower() or len(r) > 100

    def test_tool_obsidian_search(self):
        r = dispatch_tool("obsidian_search", {"query": "benchmark"})
        assert not r.startswith("[ERROR]"), f"obsidian_search failed: {r}"

    def test_tool_system_health_report(self):
        r = dispatch_tool("system_health_report", {})
        assert not r.startswith("[ERROR]"), f"system_health_report failed: {r}"
        assert "cpu" in r.lower() or "memory" in r.lower()

    def test_kimchi_provider_config(self):
        p = PROVIDER_MAP["kimchi"]
        assert p.base_url == "https://llm.kimchi.dev/openai/v1"
        assert p.is_configured
        assert p.health_endpoint is not None
        assert "kimi-k2.6" in p.models

    @pytest.mark.asyncio
    async def test_gemini_configured(self):
        p = PROVIDER_MAP["gemini"]
        assert p.is_configured
        assert len(p.api_key) > 10

    @pytest.mark.asyncio
    async def test_ollama_custom_model(self):
        p = PROVIDER_MAP["ollama"]
        assert p.is_configured
        am = ApiManager()
        assert await am.health_check(p)
