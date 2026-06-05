"""JARVIS Training — CPU-compatible LoRA fine-tuning.

Designed for Intel Iris Xe (no CUDA). Uses tiny models + small LoRA rank.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from jarvis.config import BASE_DIR

_log = logging.getLogger(__name__)

DEFAULT_BASE_MODEL: str = "Qwen/Qwen2.5-0.5B-Instruct"
DEFAULT_OUTPUT_DIR: Path = BASE_DIR / "training" / "out"


def _ensure_deps() -> None:
    try:
        import torch
        import transformers
        import peft
        import trl
    except ImportError as exc:
        raise RuntimeError(
            "Training deps missing. Install: pip install torch transformers peft trl datasets"
        ) from exc


def train_lora(
    dataset_path: Path | None = None,
    *,
    base_model: str = DEFAULT_BASE_MODEL,
    output_dir: Path | None = None,
    num_epochs: int = 1,
    batch_size: int = 1,
    lora_r: int = 4,
    lora_alpha: int = 16,
    max_seq_length: int = 128,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Fine-tune a tiny model with LoRA on CPU.

    Args:
        dataset_path: Path to JSONL with {"instruction": ..., "response": ...} rows.
        base_model: HuggingFace model ID (default: Qwen2.5-0.5B-Instruct).
        output_dir: Where to save LoRA adapters.
        num_epochs: Training epochs (default 1 for speed).
        batch_size: Per-device batch size (default 1 for CPU RAM).
        lora_r: LoRA rank (default 4 — tiny).
        lora_alpha: LoRA alpha (default 16).
        max_seq_length: Max tokens per example (default 128).
        dry_run: If True, skip actual training and return config dict.

    Returns:
        Dict with keys: output_dir, base_model, samples, status, duration_sec.
    """
    _ensure_deps()
    import time
    import torch
    from datasets import Dataset
    from peft import LoraConfig, get_peft_model, TaskType
    from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
    from trl import SFTTrainer

    t0 = time.time()
    output_dir = output_dir or DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load dataset
    if dataset_path is None:
        dataset_path = BASE_DIR / "training" / "dataset.jsonl"
    if not dataset_path.exists():
        _log.error("Dataset not found: %s", dataset_path)
        return {"status": "error", "reason": "dataset missing", "output_dir": str(output_dir)}

    with open(dataset_path, encoding="utf-8") as f:
        raw_rows = [json.loads(line) for line in f if line.strip()]

    # Format for SFTTrainer
    def format_row(row: dict) -> str:
        return (
            f"<|im_start|>system\nYou are JARVIS, a helpful OS assistant.\n<|im_end|>\n"
            f"<|im_start|>user\n{row.get('instruction', '')}\n<|im_end|>\n"
            f"<|im_start|>assistant\n{row.get('response', '')}\n<|im_end|>"
        )

    formatted = [{"text": format_row(r)} for r in raw_rows]
    dataset = Dataset.from_list(formatted)

    _log.info("Dataset loaded: %d samples", len(dataset))

    if dry_run:
        return {
            "status": "dry_run",
            "output_dir": str(output_dir),
            "base_model": base_model,
            "samples": len(dataset),
            "config": {
                "num_epochs": num_epochs,
                "batch_size": batch_size,
                "lora_r": lora_r,
                "lora_alpha": lora_alpha,
                "max_seq_length": max_seq_length,
            },
            "duration_sec": time.time() - t0,
        }

    # Load model on CPU
    _log.info("Loading model %s on CPU...", base_model)
    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        device_map="cpu",
        torch_dtype=torch.float32,
        trust_remote_code=True,
    )

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # LoRA
    lora_config = LoraConfig(
        r=lora_r,
        lora_alpha=lora_alpha,
        target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # Training args
    training_args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=num_epochs,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        logging_steps=10,
        save_strategy="epoch",
        fp16=False,
        bf16=False,
        optim="adamw_torch",
        report_to="none",
        remove_unused_columns=False,
    )

    trainer = SFTTrainer(
        model=model,
        train_dataset=dataset,
        tokenizer=tokenizer,
        args=training_args,
        max_seq_length=max_seq_length,
        dataset_text_field="text",
    )

    _log.info("Starting training for %d epochs on CPU...", num_epochs)
    trainer.train()

    # Save adapter
    adapter_dir = output_dir / "lora_adapter"
    model.save_pretrained(adapter_dir)
    tokenizer.save_pretrained(adapter_dir)
    _log.info("Adapter saved: %s", adapter_dir)

    duration = time.time() - t0
    _log.info("Training complete in %.1fs", duration)

    return {
        "status": "ok",
        "output_dir": str(output_dir),
        "adapter_dir": str(adapter_dir),
        "base_model": base_model,
        "samples": len(dataset),
        "duration_sec": duration,
    }
