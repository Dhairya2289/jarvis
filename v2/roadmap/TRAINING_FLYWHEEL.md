# TRAINING FLYWHEEL: Intelligence & Speed

## The Intelligence Stack
- **L5: LLM (Claude/Gemini)**: Reasoning engine.
- **L4: Prompt + Context**: Trainable via **DSPy**.
- **L3: Routing / Classifier**: Trainable via **Sentence-Transformers**.
- **L2: Memory Retrieval**: Trainable via **Embedding fine-tuning**.
- **L1: Local Inference**: Trainable via **LoRA (Unsloth)**.
- **L0: Fast-path Router**: Rule expansion and local caching.

## Training Phases

### Phase 0: Data Flywheel
- **Goal**: Enrich `tasks.jsonl` schema (iterations, confidence, tool sequences).
- **Action**: Implement `/rate` command for Telegram/CLI to generate labeled "good/bad" data.

### Phase 1: Task Classifier (2–4 Weeks)
- **Goal**: Move from keyword matching (~70%) to Sentence-Transformers (~92%).
- **Action**: Train Logistic Regression on embedded task logs.

### Phase 2: Embedding Fine-Tuning (1–2 Months)
- **Goal**: Optimize ChromaDB for Jarvis-specific tool and task vocabulary.
- **Action**: Contrastive training on positive/negative task-pair data.

### Phase 3: Prompt Optimization (DSPy)
- **Goal**: Empirically find optimal system prompts.
- **Action**: Use DSPy to compile and bootstrap few-shot examples into the prompt.

### Phase 4: Local LoRA (3–6 Months)
- **Goal**: Zero-latency local model that knows your schemas natively.
- **Action**: Fine-tune Qwen-2.5 or Llama-3.1 on successful "good-rated" logs using Unsloth.

### Phase 5: RLAIF (4–8 Months)
- **Goal**: Continuous self-improvement loop.
- **Action**: Use Critic Agent to generate preference data for DPO training.
