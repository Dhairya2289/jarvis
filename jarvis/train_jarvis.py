try:
    from unsloth import FastLanguageModel
except ImportError:
    FastLanguageModel = None  # type: ignore
    UNSLOTH_AVAILABLE = False
else:
    UNSLOTH_AVAILABLE = True

import torch
from datasets import load_dataset
from trl import SFTTrainer
from transformers import TrainingArguments


def train_model():
    """Train a LoRA adapter using Unsloth. Call only when UNSLOTH_AVAILABLE is True."""
    if not UNSLOTH_AVAILABLE:
        raise RuntimeError(
            "unsloth is not installed. Install with: pip install unsloth"
        )

    # 1. Config
    model_name = "unsloth/Qwen2.5-7B-Instruct-bnb-4bit"
    max_seq_length = 2048

    # 2. Load Model
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_name,
        max_seq_length=max_seq_length,
        load_in_4bit=True,
    )

    # 3. Add LoRA
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        lora_alpha=16,
        lora_dropout=0,
        bias="none",
    )

    # 4. Load Data
    dataset = load_dataset("json", data_files="~/.jarvis/training_data.jsonl", split="train")

    # 5. Train
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=max_seq_length,
        args=TrainingArguments(
            per_device_train_batch_size=2,
            gradient_accumulation_steps=4,
            warmup_steps=5,
            max_steps=60,
            learning_rate=2e-4,
            fp16=not torch.cuda.is_bf16_supported(),
            bf16=torch.cuda.is_bf16_supported(),
            logging_steps=1,
            output_dir="jarvis_lora_outputs",
        ),
    )

    trainer.train()
    model.save_pretrained_gguf("jarvis_model", tokenizer, quantization_method="q4_k_m")


if __name__ == "__main__":
    train_model()