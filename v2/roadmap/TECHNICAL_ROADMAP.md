# TECHNICAL ROADMAP: Foundation to Autonomy

## Phase 0 — Foundation (Current Priority)
- [ ] **Tool Inventory**: Update `agent.py` SYSTEM_PROMPT to include all new tool categories.
- [ ] **API Rotation Manager**: Implement `api_manager.py` with quota tracking and auto-rotation (Groq, Cerebras, SambaNova).
- [ ] **Tool Expansion**: Replace current scraper with Jina Reader; add Tavily, Open-Meteo, and yfinance.
- [ ] **Session Memory**: Implement `session_memory.py` with `deque(maxlen=20)` per interface.
- [ ] **Fast-Path Router**: Create local action dispatcher in `agent.py` for milliseconds response.
- [ ] **Real Token Streaming**: Replace `.get_final_message()` with `s.text_stream` piped to HUD via SSE.
- [ ] **Fix Swarm Loop**: Ensure sub-agents can perform multi-turn reasoning.
- [ ] **_DISPATCH_EXTRA Fix**: Debug evolved tool silent failures.

## Phase 1 — True Autonomy (2–6 Weeks)
- [ ] **Vision → Act Loop**: True "Computer Use" via screenshot analysis and coordinate-based clicking.
- [ ] **HTTP API Layer**: FastAPI `/task` endpoint for external triggers (Phone/Web).
- [ ] **Autonomous Task Queue**: Overnight research processing via cron.
- [ ] **`--doctor` Preflight**: Comprehensive health check for all subsystems (FCC, Chroma, Anki, etc.).
- [ ] **Waybar Module**: Live status indicator in the Hyprland status bar.

## Phase 2 — Persistent Intelligence (1–3 Months)
- [ ] **Life State File**: `~/.jarvis/life_state.json` for long-term user context.
- [ ] **Memory Consolidation**: Auto-generate "Skills" from task history.
- [ ] **Anticipatory Execution**: Context-aware proactive triggers.
- [ ] **Knowledge Graph Auto-Growth**: Autonomous entity extraction from all tool outputs.

## Phase 3 — Self-Directed Improvement (2–4 Months)
- [ ] **Failure Pattern Analyzer**: Self-patching prompts based on logs.
- [ ] **Prompt A/B Testing**: Automated evaluation of prompt variants.
- [ ] **Performance Dashboard**: Per-tool latency and success metrics in HUD.

## Phase 4 — Scale & Local Power (3–6 Months)
- [ ] **Local LoRA Fine-Tuning**: Personal model trained on interaction history.
- [ ] **Local Fallback**: Small quantized model for zero-latency speed tasks.
- [ ] **Rust Hot Paths**: Performance-critical dispatchers moved to Rust.
