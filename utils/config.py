# utils/config.py

import os
from dotenv import load_dotenv

load_dotenv()

# ── OpenRouter ────────────────────────────────────────────────────────────────
OPENROUTER_API_KEY  = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL")
OPENROUTER_MODEL_NAME = os.getenv("OPENROUTER_MODEL_NAME")
OPENROUTER_SITE_URL = os.getenv("OPENROUTER_SITE_URL")
OPENROUTER_APP_NAME = os.getenv("OPENROUTER_APP_NAME")

# Per-agent OpenRouter keys (optional). If unset, fallback to OPENROUTER_API_KEY.
OPENROUTER_API_KEY_FINANCIAL = os.getenv("OPENROUTER_API_KEY_FINANCIAL")
OPENROUTER_API_KEY_MARKET    = os.getenv("OPENROUTER_API_KEY_MARKET")
OPENROUTER_API_KEY_SENTIMENT = os.getenv("OPENROUTER_API_KEY_SENTIMENT")

_OPENROUTER_KEY_MAP = {
    "financial": OPENROUTER_API_KEY_FINANCIAL or OPENROUTER_API_KEY,
    "market":    OPENROUTER_API_KEY_MARKET    or OPENROUTER_API_KEY,
    "sentiment": OPENROUTER_API_KEY_SENTIMENT or OPENROUTER_API_KEY,
}

# Per-agent OpenRouter models (optional). If unset, fallback to OPENROUTER_MODEL_NAME.
OPENROUTER_MODEL_NAME_FINANCIAL = os.getenv("OPENROUTER_MODEL_NAME_FINANCIAL")
OPENROUTER_MODEL_NAME_MARKET    = os.getenv("OPENROUTER_MODEL_NAME_MARKET")
OPENROUTER_MODEL_NAME_SENTIMENT = os.getenv("OPENROUTER_MODEL_NAME_SENTIMENT")
# Free models are rate-limited per model upstream, so validator/debate/grounding
# can each be pointed at a different one instead of competing for the same slot.
OPENROUTER_MODEL_NAME_VALIDATOR = os.getenv("OPENROUTER_MODEL_NAME_VALIDATOR")
OPENROUTER_MODEL_NAME_DEBATE    = os.getenv("OPENROUTER_MODEL_NAME_DEBATE")
OPENROUTER_MODEL_NAME_GROUNDING = os.getenv("OPENROUTER_MODEL_NAME_GROUNDING")
OPENROUTER_REASONING_EFFORT = os.getenv("OPENROUTER_REASONING_EFFORT")

_OPENROUTER_MODEL_MAP = {
    "financial": OPENROUTER_MODEL_NAME_FINANCIAL or OPENROUTER_MODEL_NAME,
    "market":    OPENROUTER_MODEL_NAME_MARKET    or OPENROUTER_MODEL_NAME,
    "sentiment": OPENROUTER_MODEL_NAME_SENTIMENT or OPENROUTER_MODEL_NAME,
    "validator": OPENROUTER_MODEL_NAME_VALIDATOR or OPENROUTER_MODEL_NAME,
    "debate":    OPENROUTER_MODEL_NAME_DEBATE    or OPENROUTER_MODEL_NAME,
    "grounding": OPENROUTER_MODEL_NAME_GROUNDING or OPENROUTER_MODEL_NAME,
}

# ── LM Studio (fallback local) ──────────────────────────────────────────────────────
BASE_URL = os.getenv("BASE_URL")
API_KEY  = os.getenv("API_KEY")

# ── Groq (preferred for validator/debate/mediator) ───────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_MODEL_NAME = os.getenv("GROQ_MODEL_NAME", "llama-3.3-70b-versatile")

# ── Gemini (embeddings used by the rag/ retrieval pipeline) ───────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "models/text-embedding-004")

# ── LM Studio (fallback) ──────────────────────────────────────────────────────
BASE_URL = os.getenv("BASE_URL")
API_KEY  = os.getenv("API_KEY")

# ── Gemini (embeddings used by the rag/ retrieval pipeline) ───────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "models/text-embedding-004")

# ── Agent configs ────────────────────────────────────────────────────────────
# Specialists → OpenRouter (per-agent keys + models, configurable)
# Validator/Debate/Mediator → Groq (fast LPU, deterministic)
AGENT_LLM_CONFIGS = {
    "financial": {
        "model": None,  # resolved at runtime from _OPENROUTER_MODEL_MAP
        "temperature": 0.1,
        "max_tokens": 1500,
        "provider": "openrouter",
    },
    "market": {
        "model": None,
        "temperature": 0.2,
        "max_tokens": 1500,
        "provider": "openrouter",
    },
    "sentiment": {
        "model": None,
        "temperature": 0.4,
        "max_tokens": 1800,
        "provider": "openrouter",
    },
    # Moved off Groq after the free tier's 200k tokens/day cap started failing
    # the grounding reviewer mid-run (Groq 429 "tokens per day").
    # model=None resolves to OPENROUTER_MODEL_NAME at call time.
    "validator": {
        "model": None,
        "temperature": 0.0,
        "max_tokens": 1500,
        "provider": "openrouter",
    },
    "debate": {
        "model": None,
        "temperature": 0.3,
        "max_tokens": 1600,  # claim text + verbatim citations
        "provider": "openrouter",
    },
    "grounding": {
        "model": None,
        "temperature": 0.0,
        "max_tokens": 1200,
        "provider": "openrouter",
    },
    "mediator": {
        "model": GROQ_MODEL_NAME,
        "temperature": 0.3,
        "max_tokens": 2000,
        "provider": "groq",
    },
    "default": {
        "model": OPENROUTER_MODEL_NAME,
        "temperature": 0.2,
        "max_tokens": 1000,
        "provider": "openrouter",
    },
}


def get_agent_config(agent_name: str) -> dict:
    config = dict(AGENT_LLM_CONFIGS.get(agent_name.lower(), AGENT_LLM_CONFIGS["default"]))
    # Resolve per-agent OpenRouter model if not explicitly set
    if config.get("provider") == "openrouter" and config.get("model") is None:
        config = dict(config)
        config["model"] = _OPENROUTER_MODEL_MAP.get(
            agent_name.lower(), OPENROUTER_MODEL_NAME
        )
    if config.get("provider") == "openrouter" and OPENROUTER_REASONING_EFFORT:
        if OPENROUTER_REASONING_EFFORT not in {"none", "minimal", "low", "medium", "high", "xhigh", "max"}:
            raise ValueError("Invalid OPENROUTER_REASONING_EFFORT")
        config["reasoning_effort"] = OPENROUTER_REASONING_EFFORT
    return config
