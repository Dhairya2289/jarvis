"""Tests for config module."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import config


def test_config_exports_exist():
    """All expected constants must be exported."""
    assert hasattr(config, "BASE_DIR")
    assert hasattr(config, "FCC_BASE_URL")
    assert hasattr(config, "MODELS")
    assert hasattr(config, "BLOCKED_COMMANDS")


def test_config_types():
    """Key constants must have correct types."""
    assert isinstance(config.BASE_DIR, Path)
    assert isinstance(config.FCC_BASE_URL, str)
    assert isinstance(config.MODELS, dict)
    assert isinstance(config.BLOCKED_COMMANDS, tuple)


def test_base_dir_created():
    """BASE_DIR must exist after import."""
    assert config.BASE_DIR.exists()


def test_models_has_all_tiers():
    """MODELS must contain all routing tiers."""
    expected = {"speed", "code", "logic", "research", "vision", "debate"}
    assert expected.issubset(set(config.MODELS.keys()))


def test_pydantic_settings_validation():
    """If pydantic is available, settings should validate."""
    try:
        from pydantic import BaseModel
    except ImportError:
        return  # Skip if pydantic not installed
    # Just smoke-test that the module loaded without ValidationError
    assert config is not None
