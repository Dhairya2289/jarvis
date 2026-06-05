"""Tests that all 8 ported stubs are importable and have correct signatures."""
from __future__ import annotations

import asyncio
import inspect

import pytest

from jarvis_v3 import (
    confidence,
    debate,
    episodic_memory,
    knowledge_extractor,
    life_state_manager,
    prompt_variants,
    self_evolution,
    session_memory,
)


class TestConfidence:
    def test_score_signature(self):
        sig = inspect.signature(confidence.score)
        params = list(sig.parameters)
        assert params == ["task", "response"]

    def test_score_returns_float(self):
        val = confidence.score("test", "response")
        assert isinstance(val, float)
        assert 0.0 <= val <= 1.0


class TestDebate:
    def test_run_debate_is_async(self):
        assert asyncio.iscoroutinefunction(debate.run_debate)

    def test_run_debate_signature(self):
        sig = inspect.signature(debate.run_debate)
        params = list(sig.parameters)
        assert "question" in params


class TestEpisodicMemory:
    def test_store_and_retrieve(self):
        episodic_memory.store_successful_task("test task", ["tool1"])
        result = episodic_memory.retrieve_past_task("test task")
        assert isinstance(result, str)


class TestKnowledgeExtractor:
    def test_extract_exists(self):
        assert callable(knowledge_extractor.extract_and_add_to_graph)


class TestLifeStateManager:
    def test_get_identity_context(self):
        ctx = life_state_manager.get_identity_context()
        assert isinstance(ctx, str)
        assert "User" in ctx or "Dhairya" in ctx


class TestPromptVariants:
    def test_get_random_variant(self):
        vid, text = prompt_variants.get_random_variant()
        assert isinstance(vid, str)
        assert isinstance(text, str)

    def test_log_experiment(self):
        prompt_variants.log_experiment("test", "v1")


class TestSelfEvolution:
    def test_attempt_self_evolution(self):
        result = self_evolution.attempt_self_evolution("task", "error")
        assert isinstance(result, str)


class TestSessionMemory:
    def test_session_roundtrip(self):
        session_memory.add_session_turn("test_session", "user", "hello")
        ctx = session_memory.get_session_context("test_session")
        assert isinstance(ctx, list)
        assert any(m["content"] == "hello" for m in ctx)
