"""Tests for training pipeline."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from jarvis.training.data_collector import collect_dataset, load_dataset, save_dataset
from jarvis.training.trainer import train_lora


class TestDataCollector:
    def test_empty_dataset(self):
        pairs = collect_dataset()
        assert isinstance(pairs, list)

    def test_save_and_load(self, tmp_path: Path):
        pairs = [
            {"instruction": "hello", "response": "hi"},
            {"instruction": "bye", "response": "cya"},
        ]
        path = save_dataset(pairs, tmp_path / "ds.jsonl")
        loaded = load_dataset(path)
        assert len(loaded) == 2
        assert loaded[0]["instruction"] == "hello"


class TestTrainer:
    def test_dry_run(self, tmp_path: Path):
        # Create minimal dataset
        ds = tmp_path / "ds.jsonl"
        with ds.open("w") as f:
            f.write(json.dumps({"instruction": "test", "response": "ok"}) + "\n")
        result = train_lora(ds, output_dir=tmp_path / "out", num_epochs=1, dry_run=True)
        assert result["status"] == "dry_run"
        assert result["samples"] == 1
        assert result["config"]["lora_r"] == 4

    def test_missing_dataset(self, tmp_path: Path):
        result = train_lora(tmp_path / "nope.jsonl", dry_run=True)
        assert result["status"] == "error"
