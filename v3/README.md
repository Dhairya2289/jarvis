# JARVIS V3 — Async-First Personal AI OS

> Your autonomous AI operating system for CachyOS Linux + Hyprland. Combines the best of OpenJarvis (packaging, evaluation), your personal V2 (multi-model routing, voice, HUD), and ideas from usejarvis.dev (workflows, screen region).

## Install

```bash
cd /home/dhairya/Projects/Jarvis/V3
pip install -e .
```

Or use `uv`:

```bash
uv pip install -e .
```

## Configure

Create `~/.jarvis/.env`:

```bash
mkdir -p ~/.jarvis
cat > ~/.jarvis/.env << 'EOF'
# Required: at least one provider
GROQ_API_KEY=your_groq_key
OPENROUTER_API_KEY=your_openrouter_key
GITHUB_TOKEN=your_github_token
SAMBANOVA_API_KEY=your_sambanova_key

# Optional: local FCC proxy
FCC_BASE_URL=http://127.0.0.1:8082
FCC_AUTH_TOKEN=freecc

# Telegram bot (optional)
TELEGRAM_TOKEN=your_telegram_token
ALLOWED_USER_IDS=123456789
EOF
```

## Quick Start

```bash
# Interactive shell
jarvis-v3

# One-shot task
jarvis-v3 "turn the volume up"

# Doctor: check provider health
jarvis-v3 --doctor

# Launch HUD
jarvis-v3 --hud

# Vision: capture screen and ask AI
jarvis-v3 --vision

# Run a workflow
jarvis-v3 workflow run examples/workflows/morning_brief.yaml

# Schedule a workflow
jarvis-v3 workflow schedule examples/workflows/morning_brief.yaml
```

## Architecture

```
jarvis-v3
├── src/jarvis_v3/
│   ├── agent.py          # Async agent loop with tool execution
│   ├── api_manager.py    # Multi-provider async rotation (httpx, circuit breaker, cache)
│   ├── orchestrator.py   # Task classification + experience-based routing
│   ├── tools.py          # 12 built-in tools + _DISPATCH_EXTRA hook
│   ├── fast_path_router.py  # Local OS command fast-path (zero LLM latency)
│   ├── cli.py            # Rich interactive CLI
│   ├── gui_server.py     # FastAPI HUD backend (/api/stats, /api/agents, /api/stream)
│   ├── screen_region.py  # mss + grim screen capture
│   ├── vision_tool.py    # Vision model query via ApiManager
│   ├── workflows/        # YAML-based DAG workflow engine
│   │   ├── schema.py     # Pydantic models
│   │   ├── loader.py     # YAML parser
│   │   ├── engine.py     # Async DAG executor
│   │   └── scheduler.py  # Cron scheduler
│   └── specialists/      # Pro-workflow-based specialist prompts
│       ├── orchestrator.md
│       ├── planner.md
│       ├── debugger.md
│       ├── reviewer.md
│       └── scout.md
├── tests/                # 45 pytest tests
├── examples/workflows/   # Sample workflows
└── static/hud.html       # Real-time cyberpunk HUD
```

## Key Features

| Feature | Status |
|---------|--------|
| Async multi-provider API rotation (8 providers) | ✅ |
| Circuit breaker + rate limiter + response cache | ✅ |
| Health probes + `jarvis-v3 --doctor` | ✅ |
| 12 built-in tools (OS, files, bash, git, notify) | ✅ |
| Workflow engine (YAML DAGs, cron triggers) | ✅ |
| Screen capture → vision model (mss/grim) | ✅ |
| Real-time HUD (psutil stats, SSE logs) | ✅ |
| Specialist agents (orchestrator, planner, debugger, reviewer, scout) | ✅ |
| Fast-path router (volume, brightness, lock, workspace switch) | ✅ |

## Tests

```bash
cd /home/dhairya/Projects/Jarvis/V3
PYTHONPATH=src pytest tests/ -v
```

45 tests covering api_manager, tools, workflows, vision, and CLI.

## License

Apache 2.0
