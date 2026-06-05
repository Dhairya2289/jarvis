"""Global test fixtures and patches."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _patch_api_calls(monkeypatch):
    """Speed up tests by stubbing network calls."""
    import api_manager
    monkeypatch.setattr(api_manager, "call_with_rotation", lambda *a, **kw: "[MOCK]")
