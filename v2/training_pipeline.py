"""
JARVIS Training Pipeline — Unsloth LoRA
───────────────────────────────────────
Prepares Dhairya's interaction logs for local model fine-tuning.
Uses Unsloth for high-speed, low-VRAM training.
"""
import json
from pathlib import Path

BASE_DIR = Path.home() / ".jarvis"
LOG_FILE = BASE_DIR / "tasks.jsonl"
TRAIN_DATA = BASE_DIR / "training_data.jsonl"

def prepare_training_dataset():
    """Extract rated-good successes for instruction tuning."""
    if not LOG_FILE.exists():
        return "No logs to process."

    count = 0
    with open(LOG_FILE, "r") as f, open(TRAIN_DATA, "w") as out:
        for line in f:
            try:
                r = json.loads(line)
                # Only use high-quality examples
                if r.get("success") and r.get("user_rating") == "good":
                    # Format for instruction tuning
                    entry = {
                        "instruction": r["task"],
                        "input": "",
                        "output": f"Thinking: {r.get('task_type')}\n" \
                                  f"Tools: {r.get('tools_used')}\n" \
                                  f"Result: {r.get('result_preview')}"
                    }
                    out.write(json.dumps(entry) + "\n")
                    count += 1
            except Exception: continue
            
    return f"Prepared {count} high-quality training examples in {TRAIN_DATA.name}"

# Unsloth Training Script Template (for Dhairya to run on his GPU)
UNSLOTH_TEMPLATE = """
from unsloth import FastLanguageModel
import torch
from datasets import load_dataset
from trl import SFTTrainer
from transformers import TrainingArguments

# 1. Config
model_name = "unsloth/Qwen2.5-7B-Instruct-bnb-4bit"
max_seq_length = 2048

# 2. Load Model
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name = model_name,
    max_seq_length = max_seq_length,
    load_in_4bit = True,
)

# 3. Add LoRA
model = FastLanguageModel.get_peft_model(
    model,
    r = 16,
    target_modules = ["q_proj", "k_proj", "v_proj", "o_proj"],
    lora_alpha = 16,
    lora_dropout = 0,
    bias = "none",
)

# 4. Load Data
dataset = load_dataset("json", data_files="~/.jarvis/training_data.jsonl", split="train")

# 5. Train
trainer = SFTTrainer(
    model = model,
    tokenizer = tokenizer,
    train_dataset = dataset,
    dataset_text_field = "text",
    max_seq_length = max_seq_length,
    args = TrainingArguments(
        per_device_train_batch_size = 2,
        gradient_accumulation_steps = 4,
        warmup_steps = 5,
        max_steps = 60,
        learning_rate = 2e-4,
        fp16 = not torch.cuda.is_bf16_supported(),
        bf16 = torch.cuda.is_bf16_supported(),
        logging_steps = 1,
        output_dir = "jarvis_lora_outputs",
    ),
)

trainer.train()
model.save_pretrained_gguf("jarvis_model", tokenizer, quantization_method = "q4_k_m")
"""

def generate_unsloth_script():
    Path("Projects/Jarvis/V2/train_jarvis.py").write_text(UNSLOTH_TEMPLATE)
    return "Generated Unsloth training script: train_jarvis.py"

if __name__ == "__main__":
    print(prepare_training_dataset())
    print(generate_unsloth_script())
