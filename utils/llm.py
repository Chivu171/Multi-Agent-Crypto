# utils/llm.py

import hashlib
import json
import logging
import threading
import time

import openai
from openai import OpenAI
from utils.config import (
    OPENROUTER_API_KEY, OPENROUTER_BASE_URL,
    OPENROUTER_SITE_URL, OPENROUTER_APP_NAME,
    BASE_URL, API_KEY,
    GROQ_API_KEY, GROQ_BASE_URL,
    _OPENROUTER_KEY_MAP,
    get_agent_config,
)

logger = logging.getLogger(__name__)

# One policy for live and backtest: bounded attempts, bounded per-call timeout,
# and an optional wall-clock deadline shared by every call of one run/day.
MAX_ATTEMPTS = 3
CALL_TIMEOUT_SECONDS = 60
MAX_RETRY_WAIT_SECONDS = 60
TRANSIENT_API_ERRORS = {"rate_limit", "timeout", "connection", "provider_5xx"}
# Retrying cannot fix these; the caller should stop spending calls.
FATAL_API_ERRORS = {"quota", "config"}
_QUOTA_MARKERS = ("per day", "per-day", "per_day", "quota", "credits", "insufficient")


class LLMResponseError(ValueError):
    """The provider answered, but the content is unusable.

    kind: empty | truncated | no_json | schema. Never repaired into a prediction.
    """

    def __init__(self, message, kind):
        super().__init__(message)
        self.kind = kind


class IncompleteLLMResponse(LLMResponseError):
    """The provider stopped generation before the response was complete."""

    def __init__(self, message):
        super().__init__(message, "truncated")


class LLMAPIError(RuntimeError):
    """A provider call failed after the retry policy.

    kind: rate_limit | quota | timeout | connection | provider_5xx | config | unknown.
    """

    def __init__(self, kind, message, status_code=None, model=None):
        super().__init__(f"{kind}: {message}")
        self.kind = kind
        self.status_code = status_code
        self.model = model

    @property
    def fatal(self):
        return self.kind in FATAL_API_ERRORS


class DeadlineExceeded(RuntimeError):
    """The run/day time budget ran out before the pipeline finished."""


def response_error_kind(exc):
    return exc.kind if isinstance(exc, LLMResponseError) else "schema"


def provider_message(exc):
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        message = body.get("message") or body.get("error") or ""
        if isinstance(message, dict):
            message = message.get("message", "")
        raw = (body.get("metadata") or {}).get("raw") if isinstance(body.get("metadata"), dict) else None
        return f"{message} {raw or ''}".strip()[:500]
    return str(exc)[:500]


def classify_api_error(exc):
    if isinstance(exc, openai.APITimeoutError):
        return "timeout"
    if isinstance(exc, openai.APIConnectionError):
        return "connection"
    status = getattr(exc, "status_code", None)
    text = f"{exc} {provider_message(exc)}".lower()
    if status == 402 or (status == 429 and any(m in text for m in _QUOTA_MARKERS)):
        return "quota"
    if status == 429:
        return "rate_limit"
    if status is not None and status >= 500:
        return "provider_5xx"
    if status in (400, 401, 403, 404, 422):
        return "config"
    return "unknown"


# ── Time budget ──────────────────────────────────────────────────────────────
_deadline = None


def set_deadline(seconds):
    """Limit all following calls to `seconds` from now; None removes the limit."""
    global _deadline
    _deadline = None if seconds is None else time.monotonic() + seconds


def remaining_seconds():
    return None if _deadline is None else _deadline - time.monotonic()


def _retry_after(exc):
    response = getattr(exc, "response", None)
    try:
        return float(response.headers.get("retry-after"))
    except (AttributeError, TypeError, ValueError):
        return None


# ── Audit hooks (scripts/evaluate_direction.py replaces them) ───────────────
_local = threading.local()


def request_key(base_url, kwargs):
    return hashlib.sha256(json.dumps({"base_url": str(base_url), **kwargs}, sort_keys=True).encode()).hexdigest()


def _send(client, **kwargs):
    return client.chat.completions.create(**kwargs)


def _on_rejected(key, reason):
    """Called when the content of a completed request failed validation."""


def reject_last_response(reason):
    """Report that this thread's last completion was unusable so no cache replays it."""
    key = getattr(_local, "last_request", None)
    _local.last_request = None
    if key is not None:
        _on_rejected(key, reason)


# LM Studio client (fallback local)
_lmstudio_client = OpenAI(base_url=BASE_URL, api_key=API_KEY)

# Groq client (optional; roles use OpenRouter by default)
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
    api_key = _OPENROUTER_KEY_MAP.get(agent_name.lower()) or OPENROUTER_API_KEY
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


def _create_completion(client: OpenAI, **kwargs):
    """Retry only transient errors, within MAX_ATTEMPTS and the deadline."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        remaining = remaining_seconds()
        if remaining is not None and remaining <= 1:
            raise DeadlineExceeded("Time budget exhausted before LLM call")
        timeout = CALL_TIMEOUT_SECONDS if remaining is None else min(CALL_TIMEOUT_SECONDS, remaining)
        try:
            return _send(client.with_options(timeout=timeout, max_retries=0), **kwargs)
        except openai.APIError as exc:
            kind = classify_api_error(exc)
            error = LLMAPIError(kind, provider_message(exc), getattr(exc, "status_code", None), kwargs.get("model"))
            if kind not in TRANSIENT_API_ERRORS or attempt == MAX_ATTEMPTS:
                raise error from exc
            wait = min(_retry_after(exc) or 5 * 2 ** (attempt - 1), MAX_RETRY_WAIT_SECONDS)
            remaining = remaining_seconds()
            if remaining is not None and wait >= remaining - 1:
                raise DeadlineExceeded(f"No time left to retry {error}") from exc
            logger.warning("%s (%s); retry %d/%d after %.0fs", kind, kwargs.get("model"),
                           attempt, MAX_ATTEMPTS - 1, wait)
            time.sleep(wait)


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

    options = {}
    if provider == "openrouter" and config.get("reasoning_effort"):
        options["extra_body"] = {"reasoning": {"effort": config["reasoning_effort"]}}
    request = dict(
        model=config["model"],
        temperature=config["temperature"],
        max_tokens=config["max_tokens"],
        messages=messages,
        **options,
    )
    _local.last_request = None
    response = _create_completion(client, **request)
    _local.last_request = request_key(getattr(client, "base_url", ""), request)

    if not response.choices:
        reject_last_response("no choices")
        raise LLMResponseError(f"{agent_name}: LLM returned no choices", "empty")
    choice = response.choices[0]
    if choice.finish_reason == "length":
        reject_last_response("finish_reason=length")
        raise IncompleteLLMResponse(
            f"{agent_name}: LLM response truncated (finish_reason=length, "
            f"max_tokens={config['max_tokens']})"
        )
    content = (choice.message.content or "").strip()
    if not content:
        reject_last_response("empty content")
        raise LLMResponseError(f"{agent_name}: LLM returned empty content", "empty")
    return content
