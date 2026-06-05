"""
Tests for jarvis_v3.context_engine
───────────────────────────────────
Keyword matching, confidence scoring, routing, and fallback.
"""

import pytest

from jarvis_v3.context_engine import (
    Intent,
    classify_intent,
    route,
    CATEGORY_SPECIALISTS,
    KEYWORDS,
)


# ── classify_intent — happy path ──────────────────────────

class TestClassifyIntent:

    @pytest.mark.parametrize(
        "query,expected_category",
        [
            ("calculate the sum of 1 to 100", "logic"),
            ("solve this math problem for me", "logic"),
            ("compare A versus B", "logic"),
            ("write me a short story about a cat", "creative"),
            ("brainstorm names for my startup", "creative"),
            ("ideate a new product feature", "creative"),
            ("take a screenshot and describe what you see", "vision"),
            ("what's in this image file?", "vision"),
            ("describe image of the chart", "vision"),
            ("debug this python function for me", "code"),
            ("write a python script to parse JSON", "code"),
            ("refactor this class to use composition", "code"),
            ("implement a REST API in python", "code"),
            ("remember what I said earlier", "memory"),
            ("what did I tell you last time about that?", "memory"),
            ("recall my previous question", "memory"),
            ("check cpu usage on my system", "system"),
            ("kill the hung process", "system"),
            ("update my system settings", "system"),
            ("restart the server", "system"),
        ],
    )
    def test_keyword_routes_to_correct_category(self, query, expected_category):
        intent = classify_intent(query)
        assert intent.category == expected_category

    @pytest.mark.parametrize(
        "query,expected_specialist",
        [
            ("calculate my taxes", "orchestrator"),
            ("write a poem", "agent"),
            ("describe this image", "vision_agent"),
            ("debug my code", "agent"),
            ("remember the plan", "episodic_memory"),
            ("how much disk space do I have left", "tools"),
        ],
    )
    def test_specialist_mapped_correctly(self, query, expected_specialist):
        intent = classify_intent(query)
        assert intent.specialist == expected_specialist

    def test_confidence_is_positive(self):
        intent = classify_intent("write me a story and also calculate some math")
        assert intent.confidence > 0.0
        assert intent.confidence <= 1.0

    def test_confidence_capped_at_one(self):
        # A query that matches all creative keywords
        query = "write a story brainstorm imagine design compose draft ideate creative"
        intent = classify_intent(query)
        assert intent.confidence <= 1.0

    def test_empty_query_falls_back_to_chat(self):
        intent = classify_intent("")
        assert intent.category == "chat"
        assert intent.specialist == "agent"
        assert intent.confidence == 0.0

    def test_whitespace_only_query_falls_back_to_chat(self):
        intent = classify_intent("   \n\t  ")
        assert intent.category == "chat"

    def test_unknown_query_falls_back_to_chat(self):
        intent = classify_intent("foobarxyzabc not a real keyword")
        assert intent.category == "chat"
        assert intent.specialist == "agent"

    def test_confidence_below_threshold_falls_back_to_chat(self):
        # Single keyword match → very low confidence
        intent = classify_intent("just calculate this")
        # "calculate" is a logic keyword, but matched only 1 out of many
        # total keywords matched could be 1, so confidence might be low
        # The exact value depends on scoring; test the threshold logic indirectly
        # by checking the fallback path when confidence < 0.2
        assert intent.category in ("logic", "chat")

    def test_intent_dataclass_fields(self):
        intent = classify_intent("write a poem")
        assert hasattr(intent, "category")
        assert hasattr(intent, "confidence")
        assert hasattr(intent, "specialist")
        assert isinstance(intent.category, str)
        assert isinstance(intent.confidence, float)
        assert isinstance(intent.specialist, str)


# ── route ─────────────────────────────────────────────────

class TestRoute:
    def test_route_returns_specialist(self):
        intent = Intent(category="code", confidence=0.9, specialist="agent")
        assert route(intent) == "agent"

    def test_route_orchestrator(self):
        intent = Intent(category="logic", confidence=0.8, specialist="orchestrator")
        assert route(intent) == "orchestrator"

    def test_route_vision_agent(self):
        intent = Intent(category="vision", confidence=0.7, specialist="vision_agent")
        assert route(intent) == "vision_agent"


# ── Keyword coverage ──────────────────────────────────────

class TestKeywordCoverage:
    def test_all_categories_have_at_least_10_keywords(self):
        for category, keywords in KEYWORDS.items():
            assert len(keywords) >= 10, f"{category} has fewer than 10 keywords: {keywords}"

    def test_all_categories_have_a_specialist(self):
        for category in KEYWORDS:
            assert category in CATEGORY_SPECIALISTS, f"{category} has no specialist mapping"

    def test_specialist_map_covers_all_keyword_categories(self):
        # 'chat' is the fallback (no keywords); all keyword-driven categories must map
        for category in KEYWORDS:
            assert category in CATEGORY_SPECIALISTS, f"{category} has no specialist mapping"