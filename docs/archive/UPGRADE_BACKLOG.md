# JARVIS V2 Engineering Queue

## P0 - Foundation & Intelligence (Current)
- [ ] **Tool Inventory**: Update `agent.py` SYSTEM_PROMPT to include all tool categories (`os_hardware_control`, `media_control`, etc.).
- [ ] **API Rotation Manager**: Implement `api_manager.py` to rotate between Groq, Cerebras, SambaNova, etc.
- [ ] **Search & Scrape Upgrade**: Integrate Tavily (Search) and Jina Reader (Scrape).
- [ ] **Session Memory**: Implement `session_memory.py` for multi-turn context.
- [ ] **Fast-Path Router**: Implement local action router to skip LLM for volume/lock/time/etc.
- [ ] **Real Token Streaming**: Update `agent.py` to pipe `s.text_stream` to HUD/CLI.
- [ ] **Flywheel Data**: Enrich `tasks.jsonl` schema and add `/rate` command to Telegram.
- [ ] **Preflight Doctor**: Implement `python jarvis_cli.py --doctor` to check system health.

## P1 - Speed & Reliability
- [ ] **Fuzzy Cache**: Implement embedding-based similarity cache for common queries.
- [ ] **Hybrid Classifier**: Move from keywords to Sentence-Transformers.
- [ ] **Structured Errors**: Handle provider/sandbox failures with specific error types.
- [ ] **Task Timeouts**: Implement per-route timeouts to prevent agent hangs.

## P2 - Features & UX
- [ ] **Vision Loop**: Implement initial Computer Use (Screenshot -> Vision -> Coordinate Click).
- [ ] **HTTP API Layer**: FastAPI server for remote task execution.
- [ ] **Waybar Integration**: Live status in Hyprland status bar.
- [ ] **Obsidian Deep Index**: Better RAG for personal notes.
- [ ] **Swarm Panel**: Real-time delegation state in HUD.
