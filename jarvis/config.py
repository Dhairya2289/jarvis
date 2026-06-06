"""
JARVIS V3 — Master Configuration
All secrets via ~/.jarvis/.env — NEVER hardcode tokens here.
Enhanced with provider health-check endpoints for async API manager.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, List, Optional

from dotenv import load_dotenv

# ── Load .env ─────────────────────────────────────────────
_ENV = Path.home() / ".jarvis" / ".env"
if _ENV.exists():
    load_dotenv(_ENV)

# ── Key rotation state ────────────────────────────────────
_CASTAI_KEY_INDEX: int = 0


# ── Provider Config ───────────────────────────────────────

@dataclass(frozen=True)
class Provider:
    """A single LLM provider with routing metadata."""

    name: str
    base_url: str
    api_key_env: str
    models: List[str]  # [primary, fallback, ...]
    rpm_limit: int
    rpd_limit: int
    best_for: List[str]  # e.g. ["speed", "code"]
    health_endpoint: Optional[str] = None
    # health_endpoint is a cheap URL we can probe to check liveness
    # (e.g. groq doesn't have one, so we use a tiny chat completion)

    @property
    def api_key(self) -> str:
        global _CASTAI_KEY_INDEX
        val = os.environ.get(self.api_key_env, "")
        if self.name == "castai":
            keys = [
                k for i in range(1, 7)
                if (k := os.environ.get(f"CASTAI_API_KEY_{i}"))
            ]
            # Also include the CLI key from ~/.config/kimchi/config.json
            try:
                config_path = Path.home() / ".config" / "kimchi" / "config.json"
                if config_path.exists():
                    cfg = json.load(open(config_path))
                    cli_key = cfg.get("apiKey", "")
                    if cli_key and cli_key not in keys:
                        keys.append(cli_key)
            except Exception:
                pass
            if keys:
                idx = _CASTAI_KEY_INDEX % len(keys)
                _CASTAI_KEY_INDEX = (_CASTAI_KEY_INDEX + 1) % len(keys)
                return keys[idx]
        return val

    @property
    def is_configured(self) -> bool:
        if self.name == "ollama":
            return True  # local, no key needed
        return bool(self.api_key)


PROVIDERS: List[Provider] = [
    Provider(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY",
        models=["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
        rpm_limit=30,
        rpd_limit=14400,
        best_for=["speed", "code"],
        health_endpoint="https://api.groq.com/openai/v1/models",
    ),
    Provider(
        name="cerebras",
        base_url="https://api.cerebras.ai/v1",
        api_key_env="CEREBRAS_API_KEY",
        models=["llama-3.3-70b", "llama3.1-8b"],
        rpm_limit=30,
        rpd_limit=25000,
        best_for=["speed"],
        health_endpoint="https://api.cerebras.ai/v1/models",
    ),
    Provider(
        name="gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        api_key_env="GEMINI_API_KEY",
        models=["gemini-2.0-flash", "gemini-2.0-flash-lite"],
        rpm_limit=15,
        rpd_limit=1500,
        best_for=["vision", "research"],
        health_endpoint=None,  # uses key-append style
    ),
    Provider(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        models=["deepseek/deepseek-r1:free", "deepseek/deepseek-v3:free"],
        rpm_limit=20,
        rpd_limit=1000,
        best_for=["logic", "debate", "research"],
        health_endpoint="https://openrouter.ai/api/v1/models",
    ),
    Provider(
        name="sambanova",
        base_url="https://api.sambanova.ai/v1",
        api_key_env="SAMBANOVA_API_KEY",
        models=["Meta-Llama-3.3-70B-Instruct", "Meta-Llama-3.1-405B-Instruct"],
        rpm_limit=30,
        rpd_limit=10000,
        best_for=["logic", "research"],
        health_endpoint="https://api.sambanova.ai/v1/models",
    ),
    Provider(
        name="github",
        base_url="https://models.inference.ai.azure.com",
        api_key_env="GITHUB_TOKEN",
        models=["gpt-4o", "Meta-Llama-3.1-70B-Instruct"],
        rpm_limit=10,
        rpd_limit=150,
        best_for=["code", "logic", "vision"],
        health_endpoint="https://models.inference.ai.azure.com/models",
    ),
    Provider(
        name="fcc",
        base_url="http://127.0.0.1:8082",
        api_key_env="FCC_AUTH_TOKEN",
        models=["claude-3-5-sonnet-20241022"],
        rpm_limit=20,
        rpd_limit=500,
        best_for=["logic", "code"],
        health_endpoint="http://127.0.0.1:8082/v1/models",
    ),
    Provider(
        name="together",
        base_url="https://api.together.xyz/v1",
        api_key_env="TOGETHER_API_KEY",
        models=["meta-llama/Llama-3.3-70B-Instruct-Turbo", "mistralai/Mistral-7B-Instruct-v0.3"],
        rpm_limit=30,
        rpd_limit=1000,
        best_for=["speed", "code"],
        health_endpoint=None,
    ),
    Provider(
        name="fireworks",
        base_url="https://api.fireworks.ai/inference/v1",
        api_key_env="FIREWORKS_API_KEY",
        models=["accounts/fireworks/models/llama-v3p3-70b-instruct", "accounts/fireworks/models/mixtral-8x22b-instruct"],
        rpm_limit=30,
        rpd_limit=1000,
        best_for=["code", "logic"],
        health_endpoint=None,
    ),
    Provider(
        name="perplexity",
        base_url="https://api.perplexity.ai",
        api_key_env="PERPLEXITY_API_KEY",
        models=["sonar-pro", "sonar"],
        rpm_limit=30,
        rpd_limit=1000,
        best_for=["research"],
        health_endpoint=None,
    ),
    Provider(
        name="mistral",
        base_url="https://api.mistral.ai/v1",
        api_key_env="MISTRAL_API_KEY",
        models=["mistral-large-latest", "codestral-latest", "mistral-medium-latest"],
        rpm_limit=30,
        rpd_limit=1000,
        best_for=["code", "logic"],
        health_endpoint="https://api.mistral.ai/v1/models",
    ),
    Provider(
        name="anthropic",
        base_url="https://api.anthropic.com/v1",
        api_key_env="ANTHROPIC_API_KEY",
        models=["claude-3-5-sonnet-20241022", "claude-3-opus-20240229"],
        rpm_limit=20,
        rpd_limit=500,
        best_for=["logic", "code", "vision"],
        health_endpoint=None,
    ),
    Provider(
        name="deepseek",
        base_url="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY",
        models=["deepseek-chat", "deepseek-reasoner"],
        rpm_limit=20,
        rpd_limit=500,
        best_for=["logic", "research", "debate"],
        health_endpoint=None,
    ),
    Provider(
        name="kimchi",
        base_url=os.environ.get("KIMCHI_BASE_URL", "https://llm.kimchi.dev/openai/v1"),
        api_key_env="KIMCHI_API_KEY",
        models=["kimi-k2.6", "kimi-k2.5", "nemotron-3-super-fp4", "minimax-m2.5", "minimax-m2.7"],
        rpm_limit=60,
        rpd_limit=3000,
        best_for=["logic", "code", "speed", "vision", "research", "debate"],
        health_endpoint="https://llm.kimchi.dev/openai/v1/models",
    ),
    Provider(
        name="castai",
        base_url=os.environ.get("CASTAI_BASE_URL", "https://llm.kimchi.dev/openai/v1"),
        api_key_env="CASTAI_API_KEY_1",
        models=["kimi-k2.6", "kimi-k2.5", "nemotron-3-super-fp4", "minimax-m2.5", "minimax-m2.7"],
        rpm_limit=60,
        rpd_limit=3000,
        best_for=["logic", "code", "speed", "vision", "research", "debate"],
        health_endpoint="https://llm.kimchi.dev/openai/v1/models",
    ),
    Provider(
        name="ollama",
        base_url="http://localhost:11434/v1",
        api_key_env="",
        models=["qwen2.5:3b", "phi4-mini"],
        rpm_limit=999,
        rpd_limit=999999,
        best_for=["speed", "local"],
        health_endpoint="http://localhost:11434/api/tags",
    ),
]

# Quick lookup map
PROVIDER_MAP = {p.name: p for p in PROVIDERS}

# ── Telegram ──────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
_raw_ids = os.environ.get("ALLOWED_USER_IDS", "")
ALLOWED_USER_IDS = [int(x) for x in _raw_ids.split(",") if x.strip().isdigit()]

# ── API Server ───────────────────────────────────────────
JARVIS_API_TOKEN: Final[str] = os.environ.get("JARVIS_API_TOKEN", "JARVIS_SOTA_2026")

# ── Paths ─────────────────────────────────────────────────
BASE_DIR = Path.home() / ".jarvis"
LOG_FILE = BASE_DIR / "tasks.jsonl"
DEBATE_LOG = BASE_DIR / "debate_log.jsonl"
ROUTING_LOG = BASE_DIR / "routing_stats.json"
NOTES_DIR = Path.home() / "notes"
CHROMA_DIR = BASE_DIR / "chroma_db"
KNOWLEDGE_FILE = BASE_DIR / "knowledge.json"
GRAPH_FILE = BASE_DIR / "knowledge_graph.pkl"
SANDBOX_DIR = BASE_DIR / "sandbox"
PLANS_DIR = BASE_DIR / "plans"
WORLD_CACHE = BASE_DIR / "world_cache.json"

for _d in [BASE_DIR, SANDBOX_DIR, PLANS_DIR, CHROMA_DIR, NOTES_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# ── Models — Swarm Tiers ──────────────────────────────────
# CREDITS-FREE MODE: everything defaults to local ollama.
# Set USE_PAID_PROVIDERS=1 in ~/.jarvis/.env to re-enable cloud APIs.
USE_PAID_PROVIDERS = os.environ.get("USE_PAID_PROVIDERS", "0") == "1"

BRAIN_MODEL = "ollama:qwen2.5:3b"

MODELS = {
    "speed": [
        "ollama:qwen2.5:3b",
        "kimchi:kimi-k2.5",
        "groq:llama-3.1-8b-instant",
        "cerebras:llama3.1-8b",
    ],
    "logic": [
        "ollama:qwen2.5:3b",
        "kimchi:kimi-k2.6",
        "openrouter:deepseek/deepseek-r1:free",
        "sambanova:Meta-Llama-3.1-405B-Instruct",
        "groq:llama-3.3-70b-versatile",
        "fcc:claude-3-5-sonnet-20241022",
    ],
    "code": [
        "ollama:qwen2.5:3b",
        "kimchi:minimax-m2.7",
        "groq:llama-3.3-70b-versatile",
        "github:gpt-4o",
        "fcc:claude-3-5-sonnet-20241022",
        "openrouter:deepseek/deepseek-v3:free",
    ],
    "vision": [
        "ollama:llava-phi3",
        "kimchi:kimi-k2.6",
        "gemini:gemini-2.0-flash",
        "github:gpt-4o",
        "fcc:claude-3-5-sonnet-20241022",
    ],
    "research": [
        "ollama:qwen2.5:3b",
        "kimchi:kimi-k2.6",
        "kimchi:nemotron-3-super-fp4",
        "openrouter:deepseek/deepseek-r1:free",
        "sambanova:Meta-Llama-3.3-70B-Instruct",
    ],
    "debate": [
        "ollama:qwen2.5:3b",
        "kimchi:kimi-k2.6",
        "openrouter:deepseek/deepseek-r1:free",
        "groq:llama-3.3-70b-versatile",
        "sambanova:Meta-Llama-3.1-405B-Instruct",
    ],
}

FALLBACK_MODEL = "ollama:qwen2.5:3b"
DEFAULT_MODEL = "ollama:qwen2.5:3b"
MAX_TOKENS = 8096

# ── Timeouts ──────────────────────────────────────────────
SHELL_TIMEOUT = 30
SCRAPE_TIMEOUT = 15
GEMINI_TIMEOUT = 60
VOICE_SILENCE = 1.5

# ── Safety ────────────────────────────────────────────────
BLOCKED_COMMANDS = [
    "rm -rf /",
    "rm -rf ~",
    "mkfs",
    "dd if=",
    ":(){:|:&};:",
    "sudo rm -rf",
    "chmod -R 777 /",
]

# ── Voice ─────────────────────────────────────────────────
WAKE_WORD = os.environ.get("WAKE_WORD", "hey jarvis")
TTS_ENGINE = os.environ.get("TTS_ENGINE", "piper")
PIPER_VOICE = os.environ.get("PIPER_VOICE", "en_US-lessac-medium")
VOICE_SAMPLE_RATE = 16000
VOICE_CHANNELS = 1
VOICE_BLOCK_SIZE = 512

# ── Convenience aliases (V2 compat) ───────────────────────
FCC_BASE_URL = PROVIDER_MAP["fcc"].base_url
FCC_AUTH_TOKEN = PROVIDER_MAP["fcc"].api_key

# ── Confidence thresholds ─────────────────────────────────
CONFIDENCE_RESEARCH_BELOW = 0.55
CONFIDENCE_ASK_BELOW = 0.30

# ── Debate ────────────────────────────────────────────────
DEBATE_ROUNDS = 2
DEBATE_TRIGGER_WORDS = [
    "should i",
    "is it better",
    "compare",
    "which is best",
    "recommend",
    "advise",
    "decide",
    "best way",
    "optimal",
]

# ── World model ───────────────────────────────────────────
MONITOR_URLS: list[str] = [
    u.strip()
    for u in os.environ.get("MONITOR_URLS", "").split(",")
    if u.strip()
]
MONITOR_INTERVAL: int = int(os.environ.get("MONITOR_INTERVAL", "1800"))
