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

# ── LM Studio (fallback) ──────────────────────────────────────────────────────
BASE_URL = os.getenv("BASE_URL")
API_KEY  = os.getenv("API_KEY")

# ── Gemini (embeddings used by the rag/ retrieval pipeline) ───────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "models/text-embedding-004")

# ── Agent configs — tất cả dùng OPENROUTER_MODEL_NAME ─────────────────────────
AGENT_LLM_CONFIGS = {
    "financial": {
        "model": OPENROUTER_MODEL_NAME,
        "temperature": 0.1,
        "max_tokens": 1500
    },
    "market": {
        "model": OPENROUTER_MODEL_NAME,
        "temperature": 0.2,
        "max_tokens": 1500
    },
    "sentiment": {
        "model": OPENROUTER_MODEL_NAME,
        "temperature": 0.4,
        "max_tokens": 1200
    },
    "validator": {
        "model": OPENROUTER_MODEL_NAME,
        "temperature": 0.0,
        "max_tokens": 1500
    },
    "debate": {
        "model": OPENROUTER_MODEL_NAME,
        "temperature": 0.3,
        "max_tokens": 800
    },
    "mediator": {
        "model": OPENROUTER_MODEL_NAME,
        "temperature": 0.3,
        "max_tokens": 2000
    },
    "default": {
        "model": OPENROUTER_MODEL_NAME,
        "temperature": 0.2,
        "max_tokens": 1000
    }
}

def get_agent_config(agent_name: str) -> dict:
    return AGENT_LLM_CONFIGS.get(agent_name.lower(), AGENT_LLM_CONFIGS["default"])
