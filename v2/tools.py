"""JARVIS Tools v2 — Complete Tool Registry + Dispatchers
────────────────────────────────────────────────────────
All tools the agent can call. New in v2:
  • trafilatura for clean article extraction
  • multi_scrape: scrape multiple URLs in parallel
  • rss_fetch: parse RSS feeds
  • web_diff: detect page changes
  • anki_add: create Anki flashcards
  • obsidian_note: write to Obsidian vault
  • knowledge_graph: query/add concept graph edges
  • morning_briefing: get today's task briefing
  • _DISPATCH_EXTRA: hook for self-evolved tools
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from pathlib import Path
from typing import Any, Final

import requests
from bs4 import BeautifulSoup

from config import (
    BLOCKED_COMMANDS,
    GEMINI_TIMEOUT,
    NOTES_DIR,
    SCRAPE_TIMEOUT,
    SHELL_TIMEOUT,
)
from memory import (
    add_knowledge_edge,
    get_coordinate,
    learn_coordinate,
    query_graph,
    store_lesson,
)
from episodic_memory import retrieve_past_task, store_successful_task
from sandbox import deploy_to_production, execute_sandboxed_bash
from browser_agent import run_browser_task
from tts import speak as tts_speak
import automation_hub
import speed_ops

_log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
#  Safe-tool decorator
# ═══════════════════════════════════════════════════════════
def safe_tool(func: Callable[..., str]) -> Callable[..., str]:
    """Wrap a tool executor in error handling and logging."""
    @wraps(func)
    def _wrapper(*args: Any, **kwargs: Any) -> str:
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            _log.error("Tool %s failed: %s", func.__name__, exc, exc_info=True)
            return f"[ERROR] {func.__name__}: {exc}"
    return _wrapper


# ── Runtime hook for self-evolved tools ───────────────────
_DISPATCH_EXTRA: dict[str, Callable[..., str]] = {}


# ═══════════════════════════════════════════════════════════
#  Tool Schemas
# ═══════════════════════════════════════════════════════════
TOOL_DEFINITIONS: Final[list[dict[str, Any]]] = [
    {
        "name": "desktop_notification",
        "description": "Show a desktop HUD notification.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title":   {"type": "string"},
                "message": {"type": "string"},
                "urgency": {"type": "string", "enum": ["low","normal","critical"], "default": "normal"}
            },
            "required": ["title","message"]
        }
    },
    {
        "name": "find_and_open_file",
        "description": "Locate a local file by name under the home directory and open it with the default app.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Full or partial file name to find."},
                "open": {"type": "boolean", "default": True}
            },
            "required": ["filename"]
        }
    },
    {
        "name": "lightning_play",
        "description": "Instantly play audio for a song/video query using mpv and yt-dlp.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"]
        }
    },
    {
        "name": "high_speed_plan",
        "description": "Execute a short sequence of simple shell commands quickly after safety checks.",
        "input_schema": {
            "type": "object",
            "properties": {
                "commands": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["commands"]
        }
    },
    {
        "name": "os_hardware_control",
        "description": "Control volume, brightness, Wi-Fi, Bluetooth, lock, or suspend.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "volume_up", "volume_down", "volume_set", "mute_toggle", "mic_mute_toggle",
                        "brightness_up", "brightness_down", "brightness_set",
                        "wifi_on", "wifi_off", "bluetooth_on", "bluetooth_off",
                        "suspend", "sleep", "lock"
                    ]
                },
                "value": {"type": "string", "default": ""}
            },
            "required": ["action"]
        }
    },
    {
        "name": "os_window_control",
        "description": "Control Hyprland windows and workspaces.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "close_active", "toggle_float", "toggle_fullscreen",
                        "workspace_next", "workspace_prev", "workspace_empty",
                        "move_to_workspace", "focus_app"
                    ]
                },
                "target": {"type": "string", "default": ""}
            },
            "required": ["action"]
        }
    },
    {
        "name": "os_process_control",
        "description": "Launch, kill, or list heavy processes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["launch", "kill", "list_heavy"]},
                "target": {"type": "string", "default": ""}
            },
            "required": ["action"]
        }
    },
    {
        "name": "git_ops",
        "description": "Run git status, commit, or push in a target repository.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["status", "commit", "push"]},
                "target": {"type": "string", "default": "."},
                "message": {"type": "string", "default": ""}
            },
            "required": ["action"]
        }
    },
    {
        "name": "package_ops",
        "description": "Search or install Arch packages using paru.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["search", "install"]},
                "target": {"type": "string"}
            },
            "required": ["action", "target"]
        }
    },
    {
        "name": "system_health_report",
        "description": "Return CPU, RAM, disk, and uptime diagnostics.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "media_control",
        "description": "Control active media players using playerctl.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["play", "pause", "play-pause", "next", "previous", "stop"]}
            },
            "required": ["action"]
        }
    },
    {
        "name": "speak",
        "description": "Speak text aloud via high-quality neural TTS.",
        "input_schema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"]
        }
    },
    {
        "name": "bash",
        "description": "Run a shell command on the host system.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"]
        }
    },
    {
        "name": "sandboxed_bash",
        "description": "Run bash safely inside ~/.jarvis/sandbox/. Use for untested code.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"]
        }
    },
    {
        "name": "deploy_to_system",
        "description": "Move verified file from sandbox to a system path.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename":    {"type": "string"},
                "target_path": {"type": "string"}
            },
            "required": ["filename","target_path"]
        }
    },
    {
        "name": "scrape_url",
        "description": "Scrape clean article text from a URL using trafilatura.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url":       {"type": "string"},
                "max_chars": {"type": "integer", "default": 6000}
            },
            "required": ["url"]
        }
    },
    {
        "name": "multi_scrape",
        "description": "Scrape multiple URLs in parallel. Returns combined text.",
        "input_schema": {
            "type": "object",
            "properties": {
                "urls":     {"type": "array", "items": {"type": "string"}},
                "max_each": {"type": "integer", "default": 3000}
            },
            "required": ["urls"]
        }
    },
    {
        "name": "rss_fetch",
        "description": "Fetch and parse an RSS feed. Returns latest articles.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url":   {"type": "string"},
                "limit": {"type": "integer", "default": 10}
            },
            "required": ["url"]
        }
    },
    {
        "name": "gemini_search",
        "description": "Web research via Gemini CLI with live Google Search.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"]
        }
    },
    {
        "name": "codex",
        "description": "Large-scale code generation or refactoring via Codex CLI.",
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt":      {"type": "string"},
                "working_dir": {"type": "string", "default": "~"}
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "browser_interact",
        "description": "Control a real browser: goto, click, type, wait, content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sequence": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "cmd":      {"type": "string", "enum": ["goto","click","type","wait","content","screenshot"]},
                            "val":      {"type": "string"},
                            "selector": {"type": "string"}
                        },
                        "required": ["cmd"]
                    }
                }
            },
            "required": ["sequence"]
        }
    },
    {
        "name": "write_file",
        "description": "Write or append content to a file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path":    {"type": "string"},
                "content": {"type": "string"},
                "mode":    {"type": "string", "enum": ["write","append"], "default": "write"}
            },
            "required": ["path","content"]
        }
    },
    {
        "name": "read_file",
        "description": "Read content from a file.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"]
        }
    },
    {
        "name": "take_screenshot",
        "description": "Capture the screen. Returns image path.",
        "input_schema": {
            "type": "object",
            "properties": {"filename": {"type": "string"}}
        }
    },
    {
        "name": "ocr_image",
        "description": "Extract text from an image via OCR.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"]
        }
    },
    {
        "name": "hyprland_control",
        "description": "Send hyprctl dispatch commands to control Hyprland.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"]
        }
    },
    {
        "name": "list_windows",
        "description": "List all open windows with workspace, class, title.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "human_input",
        "description": "Simulate a single mouse/keyboard action via ydotool.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["type","click","mousemove","key"]},
                "param":  {"type": "string"}
            },
            "required": ["action","param"]
        }
    },
    {
        "name": "human_batch",
        "description": "Execute a sequence of mouse/keyboard actions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "actions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": ["type","click","mousemove","key"]},
                            "param":  {"type": "string"}
                        },
                        "required": ["action","param"]
                    }
                }
            },
            "required": ["actions"]
        }
    },
    {
        "name": "remember_gui",
        "description": "Store GUI element coordinates in spatial memory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "app_class": {"type": "string"},
                "element":   {"type": "string"},
                "x":         {"type": "integer"},
                "y":         {"type": "integer"}
            },
            "required": ["app_class","element","x","y"]
        }
    },
    {
        "name": "recall_gui",
        "description": "Retrieve stored GUI element coordinates.",
        "input_schema": {
            "type": "object",
            "properties": {
                "app_class": {"type": "string"},
                "element":   {"type": "string"}
            },
            "required": ["app_class","element"]
        }
    },
    {
        "name": "store_lesson",
        "description": "Record a technical lesson learned for future recall.",
        "input_schema": {
            "type": "object",
            "properties": {
                "context": {"type": "string"},
                "mistake": {"type": "string"},
                "fix":     {"type": "string"}
            },
            "required": ["context","mistake","fix"]
        }
    },
    {
        "name": "retrieve_past_task",
        "description": "Search episodic memory for similar past tasks.",
        "input_schema": {
            "type": "object",
            "properties": {"intent": {"type": "string"}},
            "required": ["intent"]
        }
    },
    {
        "name": "store_successful_task",
        "description": "Save a successful task + action sequence to memory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "intent":  {"type": "string"},
                "actions": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["intent","actions"]
        }
    },
    {
        "name": "os_mind_meld",
        "description": "Read deep OS state: shell history, processes, errors.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "semantic_scan",
        "description": "Get JSON map of current desktop windows and layout.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "pubmed_search",
        "description": "Search 35M+ biomedical papers via PubMed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 5}
            },
            "required": ["query"]
        }
    },
    {
        "name": "arxiv_search",
        "description": "Search research preprints via arXiv.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 5}
            },
            "required": ["query"]
        }
    },
    {
        "name": "openalex_search",
        "description": "Search 250M+ academic papers via OpenAlex.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 5}
            },
            "required": ["query"]
        }
    },
    {
        "name": "yfinance_stock",
        "description": "Get real-time stock price and info.",
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"]
        }
    },
    {
        "name": "weather_forecast",
        "description": "Get weather and 3-day forecast.",
        "input_schema": {
            "type": "object",
            "properties": {"location": {"type": "string"}},
            "required": ["location"]
        }
    },
    {
        "name": "vision_click",
        "description": "Locate a UI element on screen using vision and click it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "element": {"type": "string", "description": "Description of the element to click"}
            },
            "required": ["element"]
        }
    },
    {
        "name": "delegate_swarm",
        "description": "Spawn specialist sub-agents in parallel.",
        "input_schema": {
            "type": "object",
            "properties": {
                "delegations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "role": {"type": "string", "enum": ["researcher","coder","reviewer","operator","critic","writer"]},
                            "task": {"type": "string"}
                        },
                        "required": ["role","task"]
                    }
                }
            },
            "required": ["delegations"]
        }
    },
    {
        "name": "knowledge_graph",
        "description": "Query or add to the concept knowledge graph.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action":   {"type": "string", "enum": ["query","add"]},
                "node":     {"type": "string"},
                "relation": {"type": "string"},
                "target":   {"type": "string"}
            },
            "required": ["action","node"]
        }
    },
    {
        "name": "obsidian_note",
        "description": "Create or append a note in the Obsidian vault.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title":   {"type": "string"},
                "content": {"type": "string"},
                "tags":    {"type": "array", "items": {"type": "string"}, "default": []}
            },
            "required": ["title","content"]
        }
    },
    {
        "name": "anki_add",
        "description": "Add a flashcard to Anki via AnkiConnect API.",
        "input_schema": {
            "type": "object",
            "properties": {
                "deck":    {"type": "string", "default": "Jarvis"},
                "front":   {"type": "string"},
                "back":    {"type": "string"}
            },
            "required": ["front","back"]
        }
    },
    {
        "name": "morning_briefing",
        "description": "Get today's tasks + motivational briefing.",
        "input_schema": {"type": "object", "properties": {}}
    },
]


# ═══════════════════════════════════════════════════════════
#  Tool Executors
# ═══════════════════════════════════════════════════════════
def execute_bash(command: str) -> str:
    for blocked in BLOCKED_COMMANDS:
        if blocked in command:
            return f"[BLOCKED] Dangerous command: {blocked}"
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            timeout=SHELL_TIMEOUT, executable="/bin/bash"
        )
        return (result.stdout + result.stderr)[:6000]
    except subprocess.TimeoutExpired:
        return "[ERROR] Command timed out"
    except Exception as e:
        return f"[ERROR] {e}"


def execute_notification(title: str, message: str, urgency: str = "normal") -> str:
    try:
        subprocess.run(
            ["notify-send", "-u", urgency, "-a", "Jarvis", title, message[:200]],
            check=True, timeout=5
        )
        return f"[OK] Notification: {title}"
    except Exception as e:
        return f"[ERROR] {e}"


def execute_speak(text: str) -> str:
    return tts_speak(text, blocking=False)


def execute_scrape(url: str, max_chars: int = 6000) -> str:
    """Use Jina Reader for high-quality markdown extraction, fallback to trafilatura."""
    try:
        jina_url = f"https://r.jina.ai/{url}"
        r = requests.get(jina_url, headers={"Accept": "text/plain"}, timeout=15)
        if r.status_code == 200 and len(r.text) > 200:
            return r.text[:max_chars]
    except Exception:
        pass

    try:
        import trafilatura
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(
                downloaded, include_comments=False,
                include_tables=True, no_fallback=False
            )
            if text:
                return text[:max_chars]
    except ImportError:
        pass

    try:
        r = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101"},
            timeout=SCRAPE_TIMEOUT
        )
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "aside", "header"]):
            tag.decompose()
        text = re.sub(r'\n{3,}', '\n\n', soup.get_text(separator='\n', strip=True))
        return text[:max_chars]
    except Exception as e:
        return f"[ERROR] Scrape failed: {e}"


def execute_multi_scrape(urls: list, max_each: int = 3000) -> str:
    """Scrape multiple URLs concurrently."""
    with ThreadPoolExecutor(max_workers=min(len(urls), 5)) as pool:
        results = list(pool.map(lambda u: execute_scrape(u, max_each), urls))
    parts = []
    for url, text in zip(urls, results):
        parts.append(f"--- {url} ---\n{text}")
    return "\n\n".join(parts)


def execute_rss_fetch(url: str, limit: int = 10) -> str:
    """Fetch and parse RSS feed."""
    try:
        import feedparser
        feed = feedparser.parse(url)
        items = feed.entries[:limit]
        lines = [f"📰 {feed.feed.get('title','Feed')}\n"]
        for item in items:
            title   = item.get("title", "No title")
            summary = item.get("summary", "")[:200]
            link    = item.get("link", "")
            lines.append(f"• **{title}**\n  {summary}\n  {link}")
        return "\n".join(lines)
    except ImportError:
        return "[ERROR] feedparser not installed. Run: pip install feedparser"
    except Exception as e:
        return f"[ERROR] {e}"


def execute_gemini_search(query: str) -> str:
    try:
        result = subprocess.run(
            ["gemini", "-p", query],
            capture_output=True, text=True, timeout=GEMINI_TIMEOUT
        )
        out = result.stdout.strip() or result.stderr.strip()
        return out[:6000] if out else "[GEMINI] No response"
    except FileNotFoundError:
        return "[ERROR] gemini CLI not found. Install it first."
    except Exception as e:
        return f"[ERROR] {e}"


def execute_codex(prompt: str, working_dir: str = "~") -> str:
    try:
        result = subprocess.run(
            ["codex", "--approval-mode", "full-auto", "-q", prompt],
            capture_output=True, text=True, timeout=180,
            cwd=os.path.expanduser(working_dir)
        )
        return (result.stdout + result.stderr)[:6000]
    except FileNotFoundError:
        return "[ERROR] codex CLI not found."
    except Exception as e:
        return f"[ERROR] {e}"


def execute_write_file(path: str, content: str, mode: str = "write") -> str:
    try:
        full = Path(path).expanduser()
        full.parent.mkdir(parents=True, exist_ok=True)
        if mode == "write":
            full.write_text(content)
        else:
            with open(full, "a") as fh:
                fh.write(content)
        return f"[OK] Written {len(content)} chars to {full}"
    except Exception as e:
        return f"[ERROR] {e}"


def execute_read_file(path: str) -> str:
    try:
        return Path(path).expanduser().read_text()[:8000]
    except Exception as e:
        return f"[ERROR] {e}"


def execute_screenshot(filename: str | None = None) -> str:
    try:
        scr_dir = Path.home() / "Pictures" / "Jarvis"
        scr_dir.mkdir(parents=True, exist_ok=True)
        path = scr_dir / (filename or f"scr_{int(time.time())}.png")
        subprocess.run(["grim", str(path)], check=True, timeout=5)
        if shutil.which("magick"):
            subprocess.run(
                ["magick", str(path), "-resize", "1280x", str(path)],
                check=True, timeout=10
            )
        return str(path)
    except Exception as e:
        return f"[ERROR] {e}"


def execute_ocr(path: str) -> str:
    try:
        result = subprocess.run(
            ["tesseract", os.path.expanduser(path), "stdout", "--oem", "3"],
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip() or "(No text found)"
    except Exception as e:
        return f"[ERROR] {e}"


def execute_hypr_control(command: str) -> str:
    try:
        subprocess.run(["hyprctl", "dispatch"] + command.split(), check=True)
        return f"[OK] hyprctl dispatch {command}"
    except Exception as e:
        return f"[ERROR] {e}"


def execute_list_windows() -> str:
    try:
        clients = json.loads(
            subprocess.run(["hyprctl", "clients", "-j"],
                           capture_output=True, text=True).stdout
        )
        return "\n".join(
            f"[WS{c['workspace']['id']}] {c['class']}: {c['title']}"
            for c in clients
        ) or "No windows open."
    except Exception as e:
        return f"[ERROR] {e}"


def execute_human_input(action: str, param: str) -> str:
    try:
        if action == "type":
            subprocess.run(["wl-copy"], input=param.encode(), check=True)
            subprocess.run(["ydotool", "key", "29:1", "47:1", "47:0", "29:0"], check=True)
            return f"[OK] Typed: {param[:40]}"
        cmd = ["ydotool", action]
        if action == "mousemove":
            cmd.extend(param.split())
        else:
            cmd.append(param)
        subprocess.run(cmd, check=True)
        return f"[OK] {action}: {param}"
    except Exception as e:
        return f"[ERROR] {e}"


def execute_human_batch(actions: list) -> str:
    return " | ".join(execute_human_input(a["action"], a["param"]) for a in actions)


def execute_obsidian_note(title: str, content: str, tags: list | None = None) -> str:
    try:
        tags = tags or []
        vault = NOTES_DIR
        vault.mkdir(parents=True, exist_ok=True)
        fname = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_') + ".md"
        fpath = vault / fname
        header = f"---\ntags: {json.dumps(tags)}\ncreated: {time.strftime('%Y-%m-%d')}\n---\n\n"
        mode = "a" if fpath.exists() else "w"
        with open(fpath, mode) as f:
            if mode == "w":
                f.write(header)
            f.write(f"\n{content}")
        return f"[OK] Obsidian note: {fpath}"
    except Exception as e:
        return f"[ERROR] {e}"


def execute_anki_add(front: str, back: str, deck: str = "Jarvis") -> str:
    """Add card via AnkiConnect (Anki must be open with AnkiConnect addon)."""
    payload = {
        "action": "addNote",
        "version": 6,
        "params": {
            "note": {
                "deckName": deck,
                "modelName": "Basic",
                "fields":    {"Front": front, "Back": back},
                "options":   {"allowDuplicate": False},
                "tags":      ["jarvis"]
            }
        }
    }
    try:
        r = requests.post("http://127.0.0.1:8765", json=payload, timeout=5)
        result = r.json()
        if result.get("error"):
            return f"[ANKI ERROR] {result['error']}"
        return f"[OK] Anki card added (ID: {result.get('result')})"
    except requests.ConnectionError:
        return "[ANKI] AnkiConnect not reachable. Is Anki open?"
    except Exception as e:
        return f"[ERROR] {e}"


def execute_pubmed_search(query: str, limit: int = 5) -> str:
    """Search 35M biomedical papers via PubMed."""
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    try:
        s_res = requests.get(f"{base}/esearch.fcgi", params={
            "db": "pubmed", "term": query,
            "retmax": limit, "retmode": "json"
        }).json()
        ids = s_res.get("esearchresult", {}).get("idlist", [])
        if not ids:
            return f"No results found for: {query}"
        details = requests.get(f"{base}/esummary.fcgi", params={
            "db": "pubmed", "id": ",".join(ids), "retmode": "json"
        }).json()
        results = []
        for uid in ids:
            art = details.get("result", {}).get(uid, {})
            title = art.get('title', '?')
            date  = art.get('pubdate', '?')[:4]
            results.append(f"- {title} ({date})")
        return f"PubMed Results for '{query}':\n" + "\n".join(results)
    except Exception as e:
        return f"[ERROR] PubMed search failed: {e}"


def execute_arxiv_search(query: str, limit: int = 5) -> str:
    """Search research preprints via arXiv."""
    import xml.etree.ElementTree as ET
    try:
        r = requests.get("http://export.arxiv.org/api/query", params={
            "search_query": f"all:{query}",
            "max_results": limit,
            "sortBy": "relevance"
        })
        root = ET.fromstring(r.text)
        ns = "{http://www.w3.org/2005/Atom}"
        results = []
        for entry in root.findall(f"{ns}entry"):
            title = entry.find(f"{ns}title").text.strip().replace("\n", " ")
            url   = entry.find(f"{ns}id").text.strip()
            results.append(f"- {title}\n  {url}")
        return f"arXiv Results for '{query}':\n" + "\n".join(results) if results else "No results found."
    except Exception as e:
        return f"[ERROR] arXiv search failed: {e}"


def execute_openalex_search(query: str, limit: int = 5) -> str:
    """Search 250M+ academic papers via OpenAlex."""
    try:
        r = requests.get("https://api.openalex.org/works", params={
            "search": query,
            "per_page": limit,
            "mailto": "jarvis-os@example.com"
        }, timeout=15)
        data = r.json()
        results = []
        for work in data.get("results", []):
            title = work.get("title", "Unknown Title")
            year  = work.get("publication_year", "?")
            url   = work.get("doi") or work.get("id")
            results.append(f"- {title} ({year})\n  {url}")
        return f"OpenAlex Results for '{query}':\n" + "\n".join(results) if results else "No results found."
    except Exception as e:
        return f"[ERROR] OpenAlex search failed: {e}"


def execute_yfinance(ticker: str) -> str:
    """Get stock/market info."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        inf = t.info
        return (f"**{inf.get('longName', ticker)}** ({ticker})\n"
                f"Current: {inf.get('currentPrice','?')} {inf.get('currency','?')}\n"
                f"Day High/Low: {inf.get('dayHigh','?')}/{inf.get('dayLow','?')}\n"
                f"Market Cap: {inf.get('marketCap','?')}")
    except Exception as e:
        return f"[ERROR] yfinance failed: {e}"


def execute_weather(location: str) -> str:
    """Get weather via Open-Meteo (free, no key)."""
    import httpx
    try:
        geo_url = (
            f"https://geocoding-api.open-meteo.com/v1/search"
            f"?name={location}&count=1&language=en&format=json"
        )
        with httpx.Client() as client:
            g = client.get(geo_url).json()
            if not g.get("results"):
                return f"Could not find location: {location}"
            res = g["results"][0]
            lat, lon = res["latitude"], res["longitude"]
            w_url = (
                f"https://api.open-meteo.com/v1/forecast"
                f"?latitude={lat}&longitude={lon}&current_weather=true"
            )
            w = client.get(w_url).json()["current_weather"]
            return f"Weather in {res['name']}, {res.get('country','')}:\n" \
                   f"{w['temperature']}°C, Wind Speed: {w['windspeed']} km/h"
    except Exception as e:
        return f"[ERROR] Weather failed: {e}"


def execute_knowledge_graph(action: str, node: str,
                            relation: str = "", target: str = "") -> str:
    if action == "add" and relation and target:
        return add_knowledge_edge(node, relation, target)
    return query_graph(node)


def execute_morning_briefing() -> str:
    try:
        from planner import get_morning_briefing
        return get_morning_briefing()
    except Exception as e:
        return f"[ERROR] {e}"


def execute_find_and_open_file(filename: str, open_file: bool = True) -> str:
    """Find files under home by name and optionally open the best match."""
    needle = filename.strip().lower()
    if not needle:
        return "[ERROR] filename is empty"
    try:
        matches = []
        skip_dirs = {".cache", ".local/share/Trash", ".git",
                     "__pycache__", "node_modules", ".venv", "venv"}
        home = Path.home()
        for path in home.rglob("*"):
            rel = path.relative_to(home)
            if any(part in skip_dirs for part in rel.parts):
                continue
            if needle in path.name.lower():
                matches.append(path)
                if len(matches) >= 10:
                    break
        if not matches:
            return f"[ERROR] No file found matching: {filename}"
        best = matches[0]
        lines = [f"{i + 1}. {p}" for i, p in enumerate(matches)]
        if open_file:
            opened = automation_hub.execute_open_file(str(best))
            lines.insert(0, opened)
        return "\n".join(lines)
    except Exception as e:
        return f"[ERROR] File search failed: {e}"


def execute_lightning_play(query: str) -> str:
    return speed_ops.execute_lightning_play(query)


def execute_high_speed_plan(commands: list) -> str:
    for command in commands:
        for blocked in BLOCKED_COMMANDS:
            if blocked in command:
                return f"[BLOCKED] Dangerous command: {blocked}"
    return speed_ops.execute_high_speed_plan(commands)


def execute_os_mind_meld() -> str:
    try:
        from omniscience import read_os_mind
        return read_os_mind()
    except Exception as e:
        return f"[ERROR] {e}"


def execute_semantic_scan() -> str:
    try:
        from semantic import execute_semantic_scan as _scan
        return _scan()
    except Exception as e:
        return f"[ERROR] {e}"


# ═══════════════════════════════════════════════════════════
#  Typed dispatch map
# ═══════════════════════════════════════════════════════════
ToolEntry = tuple[Callable[..., str], tuple[str, ...]]

_DISPATCH_MAP: Final[dict[str, ToolEntry]] = {
    "desktop_notification":   (execute_notification,         ("title", "message", "urgency")),
    "find_and_open_file":     (execute_find_and_open_file,   ("filename", "open")),
    "lightning_play":         (execute_lightning_play,       ("query",)),
    "high_speed_plan":        (execute_high_speed_plan,      ("commands",)),
    "os_hardware_control":    (automation_hub.execute_hardware, ("action", "value")),
    "os_window_control":      (automation_hub.execute_window,   ("action", "target")),
    "os_process_control":     (automation_hub.execute_process,  ("action", "target")),
    "git_ops":                (automation_hub.execute_git,      ("action", "target", "message")),
    "package_ops":            (automation_hub.execute_package,  ("action", "target")),
    "system_health_report":   (automation_hub.execute_resource_report, ()),
    "media_control":          (automation_hub.execute_media,    ("action",)),
    "speak":                  (execute_speak,                ("text",)),
    "bash":                   (execute_bash,                 ("command",)),
    "sandboxed_bash":         (execute_sandboxed_bash,       ("command",)),
    "deploy_to_system":       (deploy_to_production,         ("filename", "target_path")),
    "scrape_url":             (execute_scrape,               ("url", "max_chars")),
    "multi_scrape":           (execute_multi_scrape,         ("urls", "max_each")),
    "rss_fetch":              (execute_rss_fetch,            ("url", "limit")),
    "gemini_search":          (execute_gemini_search,        ("query",)),
    "codex":                  (execute_codex,                ("prompt", "working_dir")),
    "browser_interact":       (run_browser_task,             ("sequence",)),
    "write_file":             (execute_write_file,           ("path", "content", "mode")),
    "read_file":              (execute_read_file,            ("path",)),
    "take_screenshot":        (execute_screenshot,           ("filename",)),
    "ocr_image":              (execute_ocr,                  ("path",)),
    "hyprland_control":       (execute_hypr_control,         ("command",)),
    "list_windows":           (execute_list_windows,         ()),
    "human_input":            (execute_human_input,          ("action", "param")),
    "human_batch":            (execute_human_batch,          ("actions",)),
    "remember_gui":           (learn_coordinate,             ("app_class", "element", "x", "y")),
    "recall_gui":             (get_coordinate,               ("app_class", "element")),
    "store_lesson":           (store_lesson,                 ("context", "mistake", "fix")),
    "retrieve_past_task":     (retrieve_past_task,           ("intent",)),
    "store_successful_task":  (store_successful_task,        ("intent", "actions")),
    "os_mind_meld":           (execute_os_mind_meld,         ()),
    "semantic_scan":          (execute_semantic_scan,        ()),
    "pubmed_search":          (execute_pubmed_search,        ("query", "limit")),
    "arxiv_search":           (execute_arxiv_search,         ("query", "limit")),
    "openalex_search":        (execute_openalex_search,      ("query", "limit")),
    "yfinance_stock":         (execute_yfinance,             ("ticker",)),
    "weather_forecast":       (execute_weather,              ("location",)),
    "vision_click":           (__import__("vision_agent").execute_vision_click, ("element",)),
    "delegate_swarm":         (__import__("swarm").execute_swarm, ("delegations",)),
    "knowledge_graph":        (execute_knowledge_graph,      ("action", "node", "relation", "target")),
    "obsidian_note":          (execute_obsidian_note,        ("title", "content", "tags")),
    "anki_add":               (execute_anki_add,             ("front", "back", "deck")),
    "morning_briefing":       (execute_morning_briefing,     ()),
}


# ═══════════════════════════════════════════════════════════
#  Master Dispatcher
# ═════════════════════════════════════════════════════════==
def dispatch_tool(name: str, inputs: dict[str, Any]) -> str:
    """Route a tool call to its implementation.

    Args:
        name: The tool name (must match a key in ``TOOL_DEFINITIONS``).
        inputs: Keyword arguments from the LLM tool-use block.

    Returns:
        Tool output as a string, or ``"[ERROR] …"`` on failure.
    """
    # Self-evolved tools take priority
    if name in _DISPATCH_EXTRA:
        try:
            return _DISPATCH_EXTRA[name](**inputs)
        except Exception as exc:
            _log.error("Evolved tool %s failed: %s", name, exc, exc_info=True)
            return f"[EVOLVED TOOL ERROR] {exc}"

    entry = _DISPATCH_MAP.get(name)
    if not entry:
        return f"[ERROR] Unknown tool: {name}"

    func, arg_keys = entry
    args = []
    for key in arg_keys:
        if key == "action":
            args.append(inputs.get(key, ""))
        elif key == "value":
            args.append(inputs.get(key, ""))
        elif key == "target":
            args.append(inputs.get(key, "."))
        elif key == "message":
            args.append(inputs.get(key, ""))
        elif key == "open":
            args.append(inputs.get(key, True))
        elif key == "max_chars":
            args.append(inputs.get(key, 6000))
        elif key == "max_each":
            args.append(inputs.get(key, 3000))
        elif key == "limit":
            args.append(inputs.get(key, 10))
        elif key == "working_dir":
            args.append(inputs.get(key, "~"))
        elif key == "mode":
            args.append(inputs.get(key, "write"))
        elif key == "filename":
            args.append(inputs.get(key))
        elif key == "tags":
            args.append(inputs.get(key, []))
        elif key == "deck":
            args.append(inputs.get(key, "Jarvis"))
        elif key == "relation":
            args.append(inputs.get(key, ""))
        elif key == "target_path":
            args.append(inputs.get(key))
        else:
            args.append(inputs.get(key))

    try:
        return func(*args)
    except Exception as exc:
        _log.error("Tool %s raised %s: %s", name, type(exc).__name__, exc, exc_info=True)
        return f"[ERROR] {exc}"


__all__ = [
    "TOOL_DEFINITIONS",
    "dispatch_tool",
    "safe_tool",
    "_DISPATCH_EXTRA",
    "_DISPATCH_MAP",
    "execute_bash",
    "execute_notification",
    "execute_speak",
    "execute_scrape",
    "execute_multi_scrape",
    "execute_rss_fetch",
    "execute_gemini_search",
    "execute_codex",
    "execute_write_file",
    "execute_read_file",
    "execute_screenshot",
    "execute_ocr",
    "execute_hypr_control",
    "execute_list_windows",
    "execute_human_input",
    "execute_human_batch",
    "execute_obsidian_note",
    "execute_anki_add",
    "execute_pubmed_search",
    "execute_arxiv_search",
    "execute_openalex_search",
    "execute_yfinance",
    "execute_weather",
    "execute_knowledge_graph",
    "execute_morning_briefing",
    "execute_find_and_open_file",
    "execute_lightning_play",
    "execute_high_speed_plan",
    "execute_os_mind_meld",
    "execute_semantic_scan",
]
