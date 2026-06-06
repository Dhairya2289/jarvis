#!/bin/bash
# Background training script for JARVIS
# Runs on CPU for many hours

cd /home/dhairya/Projects/Jarvis/JARVIS
export PYTHONPATH=.
export HF_HOME=/home/dhairya/.cache/huggingface

python3 -c "
import logging
logging.basicConfig(level=logging.INFO)

from jarvis.training.trainer import train_lora
from jarvis.training.swap import export_to_ollama

# Start real training
result = train_lora(
    num_epochs=1,
    batch_size=1,
    max_seq_length=64,
    lora_r=4,
    lora_alpha=16,
    dry_run=False,
)
print(f'Training complete: {result}')

# Export to ollama
if result['status'] == 'ok':
    export_to_ollama(
        base_model='Qwen/Qwen2.5-0.5B-Instruct',
        adapter_dir=result['adapter_dir'],
        model_name='jarvis-custom-v2',
    )
    print('Exported to ollama as jarvis-custom-v2')
"
