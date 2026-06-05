"""Tests for JARVIS V3 external tool plugins."""
from __future__ import annotations

import inspect

import pytest

from jarvis.plugins import browser_use_plugin, paddleocr_plugin, prompt_optimizer_plugin


class TestBrowserUsePlugin:
    def test_browse_is_async(self):
        assert inspect.iscoroutinefunction(browser_use_plugin.browse)

    def test_run_sync_exists(self):
        assert callable(browser_use_plugin.run_sync)


class TestPaddleOcrPlugin:
    def test_extract_text_signature(self):
        sig = inspect.signature(paddleocr_plugin.extract_text)
        params = list(sig.parameters)
        assert "image_path" in params


class TestPromptOptimizerPlugin:
    def test_optimize_signature(self):
        sig = inspect.signature(prompt_optimizer_plugin.optimize)
        params = list(sig.parameters)
        assert "task" in params
        assert "initial_prompt" in params
        assert "iterations" in params

    def test_generate_variant_signature(self):
        sig = inspect.signature(prompt_optimizer_plugin.generate_variant)
        params = list(sig.parameters)
        assert "task" in params
        assert "base_prompt" in params
        assert "strategy" in params