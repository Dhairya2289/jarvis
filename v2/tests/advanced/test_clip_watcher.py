"""Tests for clip_watcher.py."""
from clip_watcher import InsightClient


def test_insight_client_detect_model():
    client = InsightClient()
    model = client._detect_model()
    assert isinstance(model, str) and model
