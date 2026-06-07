# pyrefly: ignore [missing-import]
from openai import OpenAI
from utils.config import (
    BASE_URL, API_KEY,
    OPENROUTER_API_KEY, OPENROUTER_BASE_URL,
    OPENROUTER_SITE_URL, OPENROUTER_APP_NAME,
    get_agent_config,
)

# ── OpenRouter client (ưu tiên nếu có API key) ────────────────────────────────
_openrouter_client = None
if OPENROUTER_API_KEY:
    _openrouter_client = OpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=OPENROUTER_API_KEY,
        default_headers={
            "HTTP-Referer": OPENROUTER_SITE_URL,
            "X-Title": OPENROUTER_APP_NAME,
        },
    )

# ── LM Studio client (fallback local) ─────────────────────────────────────────
_lmstudio_client = OpenAI(
    base_url=BASE_URL,
    api_key=API_KEY,
)


def ask_llm(prompt: str, agent_name: str = "default") -> str:
    """
    Gửi prompt đến LLM.
    Ưu tiên OpenRouter nếu OPENROUTER_API_KEY được cấu hình,
    fallback về LM Studio nếu không có.
    """
    config = get_agent_config(agent_name)

    if _openrouter_client is not None:
        response = _openrouter_client.chat.completions.create(
            model=config["model"],
            temperature=config["temperature"],
            max_tokens=config["max_tokens"],
            messages=[{"role": "user", "content": prompt}],
        )
    else:
        response = _lmstudio_client.chat.completions.create(
            model=config["model"],
            temperature=config["temperature"],
            max_tokens=config["max_tokens"],
            messages=[{"role": "user", "content": prompt}],
        )

    content = getattr(response.choices[0].message, "content", "") or ""
    return content.strip()