"""JARVIS v2.0 — Master Configuration

All secrets via ~/.jarvis/.env — NEVER hardcode tokens here.

This module is imported by 25+ other JARVIS modules. Backward-compatibility
of exported constants is CRITICAL. Every symbol in ``__all__`` must remain
unchanged.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Final, List

from dotenv import load_dotenv

try:
    from pydantic import BaseModel, Field, ValidationError, field_validator
except ImportError:  # pragma: no cover
    BaseModel = None  # type: ignore[assignment,misc]

# ── Module logger ─────────────────────────────────────────
_log = logging.getLogger(__name__)

# ── Load .env ─────────────────────────────────────────────
_ENV_PATH: Final = Path.home() / ".jarvis" / ".env"
if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH)
    _log.debug("Loaded env from %s", _ENV_PATH)
else:
    _log.warning("Env file not found at %s — relying on exported env vars", _ENV_PATH)


# ═══════════════════════════════════════════════════════════
#  Pydantic validation (optional — degrades gracefully)
# ═══════════════════════════════════════════════════════════
class _JarvisSettings(BaseModel):
    """Typed + validated view of runtime configuration.

    The model is instantiated at import time to catch misconfiguration
    early.  It does **not** mutate the module-level constants below;
    it merely validates them for sanity.
    """

    fcc_base_url: str = Field(default="http://127.0.0.1:8082")
    fcc_auth_token: str = Field(default="freecc")

    telegram_token: str | None = None
    allowed_user_ids: List[int] = Field(default_factory=list)

    groq_api_key: str | None = None
    cerebras_api_key: str | None = None
    sambanova_api_key: str | None = None
    openrouter_api_key: str | None = None
    github_token: str | None = None
    tavily_api_key: str | None = None
    wolfram_api_key: str | None = None

    monitor_urls: List[str] = Field(default_factory=list)
    monitor_interval: int = 1800

    wake_word: str = "hey jarvis"
    tts_engine: str = "piper"
    piper_voice: str = "en_US-lessac-medium"
    voice_sample_rate: int = 16000
    voice_channels: int = 1
    voice_block_size: int = 512
    voice_silence: float = 1.5

    max_tokens: int = 8096
    shell_timeout: int = 30
    scrape_timeout: int = 15
    gemini_timeout: int = 60

    confidence_research_below: float = 0.55
    confidence_ask_below: float = 0.30

    debate_rounds: int = 2

    @field_validator("allowed_user_ids", mode="before")
    @classmethod
    def _parse_user_ids(cls, v: object) -> List[int]:
        if isinstance(v, list):
            return [int(x) for x in v]
        if isinstance(v, str):
            return [int(x) for x in v.split(",") if x.strip().isdigit()]
        return []

    @field_validator("monitor_urls", mode="before")
    @classmethod
    def _parse_monitor_urls(cls, v: object) -> List[str]:
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        return []

    @field_validator("debate_rounds", "monitor_interval", "max_tokens", "shell_timeout", "scrape_timeout", "gemini_timeout")
    @classmethod
    def _positive_int(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("must be a positive integer")
        return v

    @field_validator("confidence_research_below", "confidence_ask_below")
    @classmethod
    def _unit_interval(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("must be between 0.0 and 1.0")
        return v


# Build the validated settings object (best-effort)
_raw_ids_str = os.environ.get("ALLOWED_USER_IDS", "")
_monitor_urls_str = os.environ.get("MONITOR_URLS", "")

try:
    if BaseModel is not None:
        _SETTINGS = _JarvisSettings(
            fcc_base_url=os.environ.get("FCC_BASE_URL", "http://127.0.0.1:8082"),
            fcc_auth_token=os.environ.get("FCC_AUTH_TOKEN", "freecc"),
            telegram_token=os.environ.get("TELEGRAM_TOKEN"),
            allowed_user_ids=_raw_ids_str,
            groq_api_key=os.environ.get("GROQ_API_KEY"),
            cerebras_api_key=os.environ.get("CEREBRAS_API_KEY"),
            sambanova_api_key=os.environ.get("SAMBANOVA_API_KEY"),
            openrouter_api_key=os.environ.get("OPENROUTER_API_KEY"),
            github_token=os.environ.get("GITHUB_TOKEN"),
            tavily_api_key=os.environ.get("TAVILY_API_KEY"),
            wolfram_api_key=os.environ.get("WOLFRAM_API_KEY"),
            monitor_urls=_monitor_urls_str,
            monitor_interval=int(os.environ.get("MONITOR_INTERVAL", "1800")),
            wake_word=os.environ.get("WAKE_WORD", "hey jarvis"),
            tts_engine=os.environ.get("TTS_ENGINE", "piper"),
            piper_voice=os.environ.get("PIPER_VOICE", "en_US-lessac-medium"),
            voice_silence=float(os.environ.get("VOICE_SILENCE", "1.5")),
            max_tokens=int(os.environ.get("MAX_TOKENS", "8096")),
            shell_timeout=int(os.environ.get("SHELL_TIMEOUT", "30")),
            scrape_timeout=int(os.environ.get("SCRAPE_TIMEOUT", "15")),
            gemini_timeout=int(os.environ.get("GEMINI_TIMEOUT", "60")),
            confidence_research_below=float(os.environ.get("CONFIDENCE_RESEARCH_BELOW", "0.55")),
            confidence_ask_below=float(os.environ.get("CONFIDENCE_ASK_BELOW", "0.30")),
            debate_rounds=int(os.environ.get("DEBATE_ROUNDS", "2")),
        )
        _log.info("Configuration validated successfully")
    else:
        _SETTINGS = None  # type: ignore[assignment]
        _log.warning("pydantic not installed — skipping configuration validation")
except ValidationError as exc:  # type: ignore[name-defined]  # pragma: no cover
    _log.error("Configuration validation failed:\n%s", exc)
    raise SystemExit(1) from exc
except Exception as exc:  # pragma: no cover
    _log.warning("Could not validate configuration: %s", exc)
    _SETTINGS = None  # type: ignore[assignment]


# ═══════════════════════════════════════════════════════════
#  Backward-compatible exported constants
# ═══════════════════════════════════════════════════════════

# ── FCC Proxy ─────────────────────────────────────────────
FCC_BASE_URL: Final[str] = os.environ.get("FCC_BASE_URL", "http://127.0.0.1:8082")
FCC_AUTH_TOKEN: Final[str] = os.environ.get("FCC_AUTH_TOKEN", "freecc")

# ── Telegram ──────────────────────────────────────────────
TELEGRAM_TOKEN: Final[str | None] = os.environ.get("TELEGRAM_TOKEN")
JARVIS_API_TOKEN: Final[str] = os.environ.get(
    "JARVIS_API_TOKEN", "JARVIS_SOTA_2026"
)
ALLOWED_USER_IDS: Final[List[int]] = [
    int(x) for x in _raw_ids_str.split(",") if x.strip().isdigit()
]

# ── API Keys ──────────────────────────────────────────────
GROQ_API_KEY: Final[str | None] = os.environ.get("GROQ_API_KEY")
CEREBRAS_API_KEY: Final[str | None] = os.environ.get("CEREBRAS_API_KEY")
SAMBANOVA_API_KEY: Final[str | None] = os.environ.get("SAMBANOVA_API_KEY")
OPENROUTER_API_KEY: Final[str | None] = os.environ.get("OPENROUTER_API_KEY")
GITHUB_TOKEN: Final[str | None] = os.environ.get("GITHUB_TOKEN")
TAVILY_API_KEY: Final[str | None] = os.environ.get("TAVILY_API_KEY")
WOLFRAM_API_KEY: Final[str | None] = os.environ.get("WOLFRAM_API_KEY")

# ── Paths ─────────────────────────────────────────────────
BASE_DIR: Final[Path] = Path.home() / ".jarvis"
LOG_FILE: Final[Path] = BASE_DIR / "tasks.jsonl"
DEBATE_LOG: Final[Path] = BASE_DIR / "debate_log.jsonl"
ROUTING_LOG: Final[Path] = BASE_DIR / "routing_stats.json"
NOTES_DIR: Final[Path] = Path.home() / "notes"
CHROMA_DIR: Final[Path] = BASE_DIR / "chroma_db"
KNOWLEDGE_FILE: Final[Path] = BASE_DIR / "knowledge.json"
GRAPH_FILE: Final[Path] = BASE_DIR / "knowledge_graph.pkl"
SANDBOX_DIR: Final[Path] = BASE_DIR / "sandbox"
PLANS_DIR: Final[Path] = BASE_DIR / "plans"
WORLD_CACHE: Final[Path] = BASE_DIR / "world_cache.json"

# Create all dirs on import
for _d in (BASE_DIR, SANDBOX_DIR, PLANS_DIR, CHROMA_DIR, NOTES_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ── Models ───────────────────────────────────────────────
BRAIN_MODEL: Final[str] = "openrouter:deepseek/deepseek-r1:free"

MODELS: Final[dict[str, list[str]]] = {
    "speed": [
        "groq:llama-3.1-8b-instant",
        "cerebras:llama3.1-8b",
        "ollama:qwen2.5:3b",
    ],
    "logic": [
        "openrouter:deepseek/deepseek-r1:free",
        "sambanova:Meta-Llama-3.1-405B-Instruct",
        "groq:llama-3.3-70b-versatile",
        "fcc:claude-3-5-sonnet-20241022",
    ],
    "code": [
        "groq:llama-3.3-70b-versatile",
        "github:gpt-4o",
        "fcc:claude-3-5-sonnet-20241022",
        "openrouter:deepseek/deepseek-v3:free",
    ],
    "vision": [
        "gemini:gemini-2.0-flash",
        "github:gpt-4o",
        "fcc:claude-3-5-sonnet-20241022",
    ],
    "research": [
        "gemini:gemini-2.5-pro",
        "openrouter:deepseek/deepseek-r1:free",
        "sambanova:Meta-Llama-3.3-70B-Instruct",
    ],
    "debate": [
        "openrouter:deepseek/deepseek-r1:free",
        "groq:llama-3.3-70b-versatile",
        "sambanova:Meta-Llama-3.1-405B-Instruct",
    ],
}

FALLBACK_MODEL: Final[str] = "ollama:phi4-mini"
DEFAULT_MODEL: Final[str] = "claude-sonnet-4-5"
MAX_TOKENS: Final[int] = 8096

# ── Timeouts ──────────────────────────────────────────────
SHELL_TIMEOUT: Final[int] = 30
SCRAPE_TIMEOUT: Final[int] = 15
GEMINI_TIMEOUT: Final[int] = 60
VOICE_SILENCE: Final[float] = 1.5

# ── Safety ────────────────────────────────────────────────
BLOCKED_COMMANDS: Final[tuple[str, ...]] = (
    "rm -rf /",
    "rm -rf ~",
    "mkfs",
    "dd if=",
    ":(){:|:&};:",
    "sudo rm -rf",
    "chmod -R 777 /",
)

# ── Voice ─────────────────────────────────────────────────
WAKE_WORD: Final[str] = os.environ.get("WAKE_WORD", "hey jarvis")
TTS_ENGINE: Final[str] = os.environ.get("TTS_ENGINE", "piper")
PIPER_VOICE: Final[str] = os.environ.get("PIPER_VOICE", "en_US-lessac-medium")
VOICE_SAMPLE_RATE: Final[int] = 16000
VOICE_CHANNELS: Final[int] = 1
VOICE_BLOCK_SIZE: Final[int] = 512

# ── World Model ───────────────────────────────────────────
MONITOR_URLS: Final[List[str]] = [
    u for u in os.environ.get("MONITOR_URLS", "").split(",") if u.strip()
]
MONITOR_INTERVAL: Final[int] = int(os.environ.get("MONITOR_INTERVAL", "1800"))

# ── Confidence thresholds ─────────────────────────────────
CONFIDENCE_RESEARCH_BELOW: Final[float] = 0.55
CONFIDENCE_ASK_BELOW: Final[float] = 0.30

# ── Debate ────────────────────────────────────────────────
DEBATE_ROUNDS: Final[int] = 2
DEBATE_TRIGGER_WORDS: Final[tuple[str, ...]] = (
    "should i",
    "is it better",
    "compare",
    "which is best",
    "recommend",
    "advise",
    "decide",
    "best way",
    "optimal",
)

# ── Public API ────────────────────────────────────────────
__all__ = [
    "FCC_BASE_URL",
    "FCC_AUTH_TOKEN",
    "TELEGRAM_TOKEN",
    "ALLOWED_USER_IDS",
    "GROQ_API_KEY",
    "CEREBRAS_API_KEY",
    "SAMBANOVA_API_KEY",
    "OPENROUTER_API_KEY",
    "GITHUB_TOKEN",
    "TAVILY_API_KEY",
    "WOLFRAM_API_KEY",
    "BASE_DIR",
    "LOG_FILE",
    "DEBATE_LOG",
    "ROUTING_LOG",
    "NOTES_DIR",
    "CHROMA_DIR",
    "KNOWLEDGE_FILE",
    "GRAPH_FILE",
    "SANDBOX_DIR",
    "PLANS_DIR",
    "WORLD_CACHE",
    "BRAIN_MODEL",
    "MODELS",
    "FALLBACK_MODEL",
    "DEFAULT_MODEL",
    "MAX_TOKENS",
    "SHELL_TIMEOUT",
    "SCRAPE_TIMEOUT",
    "GEMINI_TIMEOUT",
    "VOICE_SILENCE",
    "BLOCKED_COMMANDS",
    "WAKE_WORD",
    "TTS_ENGINE",
    "PIPER_VOICE",
    "VOICE_SAMPLE_RATE",
    "VOICE_CHANNELS",
    "VOICE_BLOCK_SIZE",
    "MONITOR_URLS",
    "MONITOR_INTERVAL",
    "CONFIDENCE_RESEARCH_BELOW",
    "CONFIDENCE_ASK_BELOW",
    "DEBATE_ROUNDS",
    "DEBATE_TRIGGER_WORDS",
]
