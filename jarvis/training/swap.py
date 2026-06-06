"""JARVIS Model Swap — Merge LoRA adapter and export to Ollama.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

from jarvis.config import BASE_DIR

_log = logging.getLogger(__name__)


def merge_adapter(
    base_model: str,
    adapter_dir: Path,
    output_dir: Path | None = None,
) -> Path:
    """Merge LoRA adapter back into the base model and save."""
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    output_dir = output_dir or (BASE_DIR / "training" / "merged")
    output_dir.mkdir(parents=True, exist_ok=True)

    _log.info("Loading base model %s...", base_model)
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        device_map="cpu",
        trust_remote_code=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)

    _log.info("Loading adapter from %s...", adapter_dir)
    model = PeftModel.from_pretrained(model, str(adapter_dir))

    _log.info("Merging adapter...")
    model = model.merge_and_unload()

    _log.info("Saving merged model to %s...", output_dir)
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

    # Preserve canonical config metadata for Ollama GGUF compatibility.
    # Training may alter eos_token_id / pad_token_id in saved configs, which
    # breaks llama.cpp's convert_hf_to_gguf. Restore original config files.
    for fname in ("config.json", "generation_config.json", "tokenizer_config.json"):
        src = Path(base_model) / fname
        dst = output_dir / fname
        if src.exists():
            _log.info("Restoring original %s", fname)
            import shutil
            shutil.copy2(str(src), str(dst))

    return output_dir


def write_modelfile(merged_dir: Path, modelfile_path: Path | None = None) -> Path:
    """Write an Ollama Modelfile referencing the merged model."""
    if modelfile_path is None:
        modelfile_path = merged_dir / "Modelfile"

    content = (
        f"FROM {merged_dir}\n"
        "\n"
        "SYSTEM \"\"\"You are JARVIS, a helpful OS assistant.\n"
        "You have been fine-tuned on the user's personal data and preferences.\n"
        "Always be concise, accurate, and context-aware.\"\"\"\n"
        "\n"
        "PARAMETER temperature 0.7\n"
        "PARAMETER num_ctx 4096\n"
        "PARAMETER stop <|endoftext|>\n"
        "PARAMETER stop </s>\n"
    )
    modelfile_path.write_text(content, encoding="utf-8")
    _log.info("Modelfile written: %s", modelfile_path)
    return modelfile_path


def create_ollama_model(
    modelfile_path: Path,
    model_name: str = "jarvis-custom",
) -> str:
    """Run `ollama create` to build a runnable model."""
    cmd = ["ollama", "create", model_name, "-f", str(modelfile_path)]
    _log.info("Running: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
            check=True,
        )
        _log.info("Ollama model created: %s", result.stdout.strip())
        return f"[OLLAMA] Created model: {model_name}"
    except subprocess.CalledProcessError as exc:
        return f"[OLLAMA ERROR] {exc.stderr.strip()}"
    except FileNotFoundError:
        return "[OLLAMA ERROR] ollama CLI not found. Install ollama first."


def export_to_ollama(
    base_model: str,
    adapter_dir: Path,
    model_name: str = "jarvis-custom",
) -> dict[str, Any]:
    """Full pipeline: merge adapter → write Modelfile → create ollama model."""
    merged = merge_adapter(base_model, adapter_dir)
    modelfile = write_modelfile(merged)
    result = create_ollama_model(modelfile, model_name=model_name)
    return {
        "merged_dir": str(merged),
        "modelfile": str(modelfile),
        "result": result,
    }
