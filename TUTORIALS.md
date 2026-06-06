# JARVIS Tutorials — Complete Feature Testing Guide

> Last updated: 2026-06-06

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Ollama Model](#ollama-model)
3. [File Search & Universal Search](#file-search--universal-search)
4. [PDF Ingestion](#pdf-ingestion)
5. [Download Organizer](#download-organizer)
6. [RSS Feed Reader](#rss-feed-reader)
7. [Smart To-Do](#smart-todo)
8. [Desktop Orchestration](#desktop-orchestration)
9. [Interactive Agent Loop](#interactive-agent-loop)
10. [Running Tests](#running-tests)

---

## Quick Start

All commands assume you're in the repo root and run with `PYTHONPATH=.`

```bash
cd /home/dhairya/Projects/Jarvis/JARVIS
```

---

## Ollama Model

### Verify the fine-tuned model works

```bash
curl -s http://localhost:11434/api/generate \
  -d '{"model":"jarvis-custom-v2","prompt":"Say hello","stream":false}' | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('response','NO CONTENT')[:80])"
```

**Expected:** real English text. If you see `????` the model is corrupted.

### Run inference via API manager (Python)

```python
PYTHONPATH=. python3 <<'PY'
from jarvis.api_manager import APIManager
mgr = APIManager()
resp = mgr.chat(
    messages=[{"role":"user","content":"Say hello"}],
    provider="ollama",
    model="jarvis-custom-v2"
)
print(resp["content"])
PY
```

---

## File Search & Universal Search

### Index your files

```bash
# Index home directory (~30s for 10k files)
PYTHONPATH=. python3 -m jarvis.cli --index-files

# Index a specific path
PYTHONPATH=. python3 -m jarvis.cli --index-files ~/Documents
```

### Search

```bash
# Universal search across files, apps, and Obsidian vault
PYTHONPATH=. python3 -m jarvis.cli --search "obsidian"

# Python API
PYTHONPATH=. python3 <<'PY'
from jarvis.universal_search import universal_search
results = universal_search("report", scopes=["files","vault"])
for r in results[:5]:
    print(f"[{r.kind}] {r.title}: {r.score:.2f}")
PY
```

---

## PDF Ingestion

### Ingest a single PDF

```bash
PYTHONPATH=. python3 -m jarvis.cli --ingest-pdf ~/Downloads/paper.pdf
```

Result appears in `~/obsidian/JARVIS/pdfs/` as markdown with YAML frontmatter.

### Batch ingest a folder

```python
PYTHONPATH=. python3 <<'PY'
from jarvis.pdf_ingestion import PDFIngestion
from pathlib import Path
results = PDFIngestion().batch_ingest(Path("~/Downloads"))
print(f"Ingested {len(results)} PDFs")
PY
```

---

## Download Organizer

```bash
# Organize ~/Downloads into sub-folders by MIME type
PYTHONPATH=. python3 -m jarvis.cli --organize-downloads
```

Categories created: `Images/`, `Documents/`, `Archives/`, `Media/`, `Code/`, `Other/`

---

## RSS Feed Reader

```bash
# Default feed (Hacker News front page)
PYTHONPATH=. python3 -m jarvis.cli --rss-digest

# Custom feeds
PYTHONPATH=. python3 -m jarvis.cli --rss-digest --feeds 'https://hnrss.org/frontpage,https://lobste.rs/rss'
```

Output is a markdown digest appended to today's Obsidian daily note.

---

## Smart To-Do

```bash
# Add from natural language
PYTHONPATH=. python3 -m jarvis.cli --add-todo "Send weekly report tomorrow, high priority"
PYTHONPATH=. python3 -m jarvis.cli --add-todo "Fix the bug in jarvis-custom-v2 by Friday ASAP"

# List open todos
PYTHONPATH=. python3 -m jarvis.cli --list-todos

# List completed todos
PYTHONPATH=. python3 -m jarvis.cli --list-todos done
```

Priority parsing: `ASAP/critical/urgent` → 🔴, `high priority` → 🟠, `medium` → 🟡, `low/no rush` → ⚪
Date parsing: `tomorrow`, `day after tomorrow`, `in 3 days`, `next Monday`, `by June 15`

Todos are stored in `~/obsidian/JARVIS/Inbox.md`.

---

## Desktop Orchestration

### Workspace Memory

```bash
# Snapshot current Hyprland workspaces
PYTHONPATH=. python3 -m jarvis.cli --snapshot

# Restore from file
PYTHONPATH=. python3 -m jarvis.cli --restore /home/dhairya/.jarvis/workspace_2026-06-06.json
```

### Smart Launcher

```bash
# Launch best-matching app
PYTHONPATH=. python3 -m jarvis.cli --launch firefox
PYTHONPATH=. python3 -m jarvis.cli --launch "obsidian"
```

### Clipboard History

```bash
# Last 10 clipboard entries
PYTHONPATH=. python3 -m jarvis.cli --clipboard-history

# Last 50
PYTHONPATH=. python3 -m jarvis.cli --clipboard-history 50
```

Requires `wl-clipboard` installed (ships with CachyOS/Wayland).

### Notification Triage

```bash
# Recent notifications
PYTHONPATH=. python3 -m jarvis.cli --notifications

# Last 20
PYTHONPATH=. python3 -m jarvis.cli --notifications 20
```

Reads mako history or queries D-Bus.

### Screenshot Manager

```bash
# Move old screenshots to archive
PYTHONPATH=. python3 -m jarvis.cli --archive-screenshots
```

Archives `~/Pictures/Screenshots/` files older than 30 days to `~/.jarvis/screenshots_archive/`.

### Window Timeline

```bash
# Last 24 hours
PYTHONPATH=. python3 -m jarvis.cli --window-timeline

# Last 4 hours
PYTHONPATH=. python3 -m jarvis.cli --window-timeline 4
```

Requires `hyprctl` (ships with Hyprland).

---

## Interactive Agent Loop

```bash
PYTHONPATH=. python3 -m jarvis.cli --loop
```

The loop:
1. Classifies your intent
2. Routes to specialist (tools / agent / vision / memory)
3. Auto-logs to Obsidian daily note + session note
4. Stores tool sequences in episodic memory

Type `quit` or `exit` to leave.

---

## Running Tests

```bash
cd /home/dhairya/Projects/Jarvis/JARVIS

# Individual modules
pytest tests/test_file_search_index.py -v
pytest tests/test_universal_search.py -v
pytest tests/test_pdf_ingestion.py -v
pytest tests/test_download_organizer.py -v
pytest tests/test_rss_reader.py -v
pytest tests/test_smart_todo.py -v
pytest tests/test_desktop_orchestration.py -v

# Core health benchmark
pytest tests/test_final_benchmark.py -v
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `No tests collected` | Use bare `pytest` binary, not `python3 -m pytest` |
| `--doctor` crashes | Known async bug in legacy CLI; use `--loop` instead |
| Clipboard empty | Install `wl-clipboard`: `sudo pacman -S wl-clipboard` |
| Hyprland tools fail | Ensure `hyprctl` is in PATH |
