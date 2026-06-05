# JARVIS — Unified AI OS

Single-package agent architecture. Async-first with sync fallbacks.

## Structure

```
JARVIS/
├── jarvis/              # Unified package (all modules)
│   ├── config.py
│   ├── agent.py
│   ├── api_manager.py
│   ├── tools.py
│   ├── obsidian_brain.py   # Canonical brain — structured markdown vault
│   ├── skill_system.py     # Auto-discovered skills
│   ├── memdir.py           # Typed memory with decay
│   ├── coordinator.py      # Multi-agent fork
│   ├── context_engine.py   # Intent classifier
│   ├── compat/             # Async↔Sync bridge
│   ├── plugins/            # External tool integrations
│   └── apps/               # Desktop app connectors
├── tests/               # Flat test suite
├── examples/            # Runnable demos
├── docs/                # Documentation + archive
└── pyproject.toml       # Project config
```

## Quick Start

```bash
pip install -e .
PYTHONPATH=. pytest tests/ -q
```

## External Tool Plugins

- **browser-use** → `jarvis_v3.plugins.browser_use_plugin`
- **PaddleOCR** → `jarvis_v3.plugins.paddleocr_plugin`
- **prompt-optimizer** → `jarvis_v3.plugins.prompt_optimizer_plugin`
