"""Smoke tests for benchmark assertions.

These mirror /tmp/benchmark_jarvis.py but as repeatable pytest cases.
"""
from __future__ import annotations

import pytest
from jarvis.config import PROVIDERS, PROVIDER_MAP, USE_PAID_PROVIDERS


class TestBenchmarkSmoke:
    def test_provider_count(self):
        assert len(PROVIDERS) == 16

    def test_all_providers_have_names(self):
        for p in PROVIDERS:
            assert p.name

    def test_castai_key_rotates(self):
        """Each access returns a different key (7 total: 6 env + 1 CLI)."""
        castai = PROVIDER_MAP["castai"]
        keys = [castai.api_key for _ in range(8)]
        assert len(set(keys)) == 7

    def test_castai_configured(self):
        castai = PROVIDER_MAP["castai"]
        assert castai.is_configured
        assert castai.base_url == "https://llm.kimchi.dev/openai/v1"

    def test_castai_models(self):
        castai = PROVIDER_MAP["castai"]
        assert "kimi-k2.6" in castai.models
        assert "minimax-m2.7" in castai.models

    def test_kimchi_configured(self):
        kimchi = PROVIDER_MAP["kimchi"]
        assert kimchi.is_configured
        assert kimchi.base_url == "https://llm.kimchi.dev/openai/v1"
        assert len(kimchi.api_key) > 10

    def test_kimchi_models(self):
        kimchi = PROVIDER_MAP["kimchi"]
        assert "kimi-k2.6" in kimchi.models
        assert "minimax-m2.7" in kimchi.models
        assert "nemotron-3-super-fp4" in kimchi.models

    def test_gemini_configured(self):
        gemini = PROVIDER_MAP["gemini"]
        assert gemini.is_configured
        assert len(gemini.api_key) > 10

    def test_openrouter_configured(self):
        orv = PROVIDER_MAP["openrouter"]
        assert orv.is_configured
        assert len(orv.api_key) > 10

    def test_paid_providers_enabled(self):
        assert USE_PAID_PROVIDERS is True

    def test_ollama_local(self):
        ollama = PROVIDER_MAP["ollama"]
        assert ollama.is_configured
        assert ollama.api_key == ""
