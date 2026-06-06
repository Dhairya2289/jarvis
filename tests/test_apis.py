"""Tests for API provider configuration and key rotation."""
from __future__ import annotations

import os

import pytest
from jarvis.config import PROVIDERS, PROVIDER_MAP


class TestProviders:
    def test_all_providers_have_name(self):
        for p in PROVIDERS:
            assert p.name

    def test_castai_configured(self):
        castai = PROVIDER_MAP.get("castai")
        assert castai is not None
        assert castai.is_configured
        assert castai.base_url == "https://llm.kimchi.dev/openai/v1"

    def test_castai_key_rotation(self):
        """Each call to .api_key should return a different key."""
        castai = PROVIDER_MAP["castai"]
        keys = [castai.api_key for _ in range(10)]
        # Should cycle through all 7 keys (6 env + 1 CLI)
        unique = set(keys)
        assert len(unique) == 7, f"Expected 7 unique keys, got {len(unique)}"

    def test_gemini_configured(self):
        gemini = PROVIDER_MAP.get("gemini")
        assert gemini is not None
        assert gemini.is_configured

    def test_openrouter_configured(self):
        orv = PROVIDER_MAP.get("openrouter")
        assert orv is not None
        assert orv.is_configured

    def test_ollama_always_configured(self):
        ollama = PROVIDER_MAP.get("ollama")
        assert ollama is not None
        assert ollama.is_configured

    def test_use_paid_providers_flag(self):
        from jarvis.config import USE_PAID_PROVIDERS
        assert isinstance(USE_PAID_PROVIDERS, bool)
