# 🚀 MASTER ROADMAP: JARVIS "Supercomputer AI" (Revised)

This document is the **definitive source of truth** for JARVIS V2. It incorporates a deep gap analysis and realistic engineering timelines.

---

## 🏗️ Intelligence Stack (Layered Architecture)
- **L5: Reasoning Engine** (Claude 3.5, DeepSeek-R1, Gemini 2.5 Pro)
- **L4: Optimization** (DSPy compiled prompts and bootstrap few-shot examples)
- **L3: Routing** (Sentence-Transformer task classifier, ~92% accuracy target)
- **L2: Memory** (Custom contrastive embeddings for ChromaDB retrieval)
- **L1: Local Core** (Raw Ollama models [phi4-mini, qwen2.5:3b] → **Phase 4 Upgrade**: Fine-tuned LoRA)
- **L0: Fast-Path** (Microsecond rule-based router and SQLite response cache)

---

## 📅 Evolutionary Phases

### Phase 0: Foundation & Always-On (Month 1)

#### Week 1: Critical Fixes & Infrastructure
*Goal: Fix the foundation and ensure Jarvis never dies.*
- [x] **Lambda Fix**: Patch `_DISPATCH_EXTRA` in `tools.py` (`lambda: fn(**{})` → `lambda **kw: fn(**kw)`).
- [x] **Systemd Services**: Create and enable services for `daemon`, `telegram`, `clip_watcher`, and `file_watcher`.
- [x] **L1 Local Fallback**: Install **Ollama** and pull `phi4-mini` (2.3GB) for offline capability.
- [x] **Always-On Environment**: Configure `tmux` for persistent dev sessions and **Tailscale** for remote access from phone.
- [x] **Tool Inventory**: Update `SYSTEM_PROMPT` in `agent.py` to include all OS, Media, and System control categories.
- [x] **Research Starter**: Replace current scraper with **Jina Reader** (zero-setup markdown extraction).

#### Week 2: Intelligence & Data Flywheel
*Goal: Stop being forgetful and start collecting training data.*
- [x] **Session Memory**: Implement `session_memory.py` with `deque(maxlen=20)` for multi-turn awareness.
- [x] **Fast-Path Router**: Add local dispatcher to handle hardware (volume/lock), time, and system health in milliseconds.
- [x] **Academic Stack**: Integrate **PubMed**, **arXiv**, and **OpenAlex** (no-key APIs) into `tools.py`.
- [x] **Data Flywheel**: Enrich `tasks.jsonl` schema and add `/rate` command to Telegram for supervised labeling.

#### Weeks 3–4: Speed & Redundancy
*Goal: Multi-provider swarm and real-time feedback.*
- [x] **API Rotation Manager**: Implement `api_manager.py` with RPM/RPD tracking for Groq, Cerebras, SambaNova, and Gemini.
- [x] **Real Token Streaming**: Replace `.get_final_message()` with `s.text_stream` piped via SSE to the Iron Man HUD.
- [x] **Financial & Weather**: Integrate **yfinance** and **Open-Meteo**.

---

### Phase 1: True Autonomy (Month 2)
*Goal: Real computer use and autonomous processing.*
- [x] **Vision → Act Loop**: True "Computer Use." Screenshot -> Vision Model -> Coordinate Calculation -> Click/Type.
- [x] **HTTP API Layer**: Build a FastAPI bridge to allow phone Shortcuts and web apps to trigger Jarvis tasks.
- [x] **Autonomous Queue**: Implement an overnight processing queue (`task_queue.jsonl`) for heavy research/coding tasks.
- [x] **Swarm Loop Fix**: Extract `agent.py` inner loop to allow sub-agents to perform multi-turn reasoning and tool use.
- [x] **Preflight Doctor**: Implement `python jarvis_cli.py --doctor` to verify all 12+ subsystems.


---

### Phase 2: Persistent Intelligence (Month 3)
*Goal: Long-term identity and proactive behavior.*
- [x] **Identity Injection**: Automate `life_state.json` updates and inject context into every request.
- [x] **Memory Consolidation**: Weekly cron to cluster task patterns and auto-generate reusable "Skills."
- [x] **Anticipatory Execution**: Proactive triggers based on file activity or desktop state.
- [x] **Knowledge Graph growth**: Extract entities from tool results to build the graph in `knowledge_graph.pkl`.

---

### Phase 3: Self-Directed Improvement (Month 4)
*Goal: Autonomous optimization using Phase 0 data.*
- [x] **Failure Pattern Analyzer**: Identify repeated tool failures and auto-patch system prompts.
- [x] **Prompt A/B Testing**: Use `/rate` data to run variants and pick winners based on user preference.
- [x] **Performance Dashboard**: Real-time tool latency and success observability in the Iron Man HUD.

---

### Phase 4: Local Power & Scale (Month 5+)
*Goal: High-performance ownership.*
- [x] **Local LoRA Fine-Tuning Pipeline**: Dataset extraction and training script generation initialized.
- [x] **RLAIF Loop**: Preference pair generation engine with Critic agent scoring.
- [x] **Multi-Machine Control**: SSH/Tailscale bridge for managing remote nodes.
- [x] **Rust Hot Paths**: High-performance core dispatchers for zero-latency OS control.

---

## 🛠️ The Comprehensive Toolset

| Category | Tools & APIs |
| :--- | :--- |
| **LLMs** | Groq, Cerebras, SambaNova, GitHub Models, Gemini, Ollama (Local) |
| **Search** | Tavily, Serper, DDG, Jina Reader |
| **Academic** | OpenAlex, PubMed, arXiv, Semantic Scholar |
| **Utility** | yfinance, Open-Meteo, Wolfram Alpha, Wikipedia |
| **Infrastructure** | systemd, tmux, Redis, Playwright, Tailscale |
| **Core Dev** | loguru, httpx, trafilatura, duckduckgo-search, rich, unsloth, DSPy |
| **Linux/CLI** | ripgrep, fd, jq, fzf, bat, rclone, Syncthing |

---
*Status: Phase 0 Started (Life State Initialized)*
