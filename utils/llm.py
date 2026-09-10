# utils/llm.py

from openai import OpenAI
from utils.config import (
    OPENROUTER_API_KEY, OPENROUTER_BASE_URL,
    OPENROUTER_SITE_URL, OPENROUTER_APP_NAME,
    BASE_URL, API_KEY,
    GROQ_API_KEY, GROQ_BASE_URL,
    _OPENROUTER_KEY_MAP,
    get_agent_config,
)

# LM Studio client (fallback local)
_lmstudio_client = OpenAI(base_url=BASE_URL, api_key=API_KEY)

# Groq client (preferred for validator/debate/mediator)
_groq_client = None
if GROQ_API_KEY:
    _groq_client = OpenAI(
        base_url=GROQ_BASE_URL,
        api_key=GROQ_API_KEY,
    )


def _get_openrouter_client(agent_name: str) -> OpenAI | None:
    """Return an OpenRouter client for the given agent.

    Preference order:
    1. Per-agent key from ``_OPENROUTER_KEY_MAP``
    2. Global ``OPENROUTER_API_KEY``
    3. ``None`` if neither is configured
    """
    api_key = _OPENROUTER_KEY_MAP.get(agent_name.lower())
    if not api_key:
        return None
    return OpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=api_key,
        default_headers={
            "HTTP-Referer": OPENROUTER_SITE_URL,
            "X-Title": OPENROUTER_APP_NAME,
        },
    )


def ask_llm(prompt: str, agent_name: str = "default", system: str | None = None) -> str:
    config = get_agent_config(agent_name)
    provider = config.get("provider", "openrouter")

    if provider == "groq" and _groq_client is not None:
        client = _groq_client
    else:
        client = _get_openrouter_client(agent_name)
        if client is None:
            client = _lmstudio_client

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=config["model"],
        temperature=config["temperature"],
        max_tokens=config["max_tokens"],
        messages=messages,
    )

    content = response.choices[0].message.content or ""
    return content.strip()
