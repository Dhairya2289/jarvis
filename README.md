# JARVIS Unified Project

Combined V2 and V3 codebase for JARVIS AI OS.

## Structure

```
JARVIS/
├── v2/              # Refined V2 modules (flat, backward-compatible)
│   ├── config.py
│   ├── agent.py
│   ├── api_manager.py
│   ├── tools.py
│   ├── orchestrator.py
│   ├── swarm.py
│   ├── planner.py
│   ├── memory.py
│   ├── daemon.py
│   ├── world_model.py
│   ├── self_evolution.py
│   ├── confidence.py
│   ├── debate.py
│   ├── ...
│   └── tests/
├── v3/              # V3 async-first architecture
│   ├── src/jarvis_v3/
│   │   ├── config.py
│   │   ├── agent.py
│   │   ├── api_manager.py
│   │   ├── tools.py
│   │   ├── compat/       # V2↔V3 bridge
│   │   └── plugins/      # External tool integrations
│   └── tests/
├── examples/         # Runnable demos
├── docs/             # Audit reports and documentation
└── pyproject.toml    # Unified project config
```

## Testing

```bash
# V2 tests
PYTHONPATH=v2 pytest v2/tests/ -v

# V3 tests
PYTHONPATH=v3/src pytest v3/tests/ -v
```

## External Tool Plugins

- **browser-use** → `jarvis_v3.plugins.browser_use_plugin`
- **PaddleOCR** → `jarvis_v3.plugins.paddleocr_plugin`
- **prompt-optimizer** → `jarvis_v3.plugins.prompt_optimizer_plugin`
