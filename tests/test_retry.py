"""Verify the shared retry policies in utils/retry.py actually retry —
not just that they import cleanly. Uses `.retry.copy(wait=wait_fixed(0))`
to skip tenacity's real sleep during tests (the production wait_exponential
schedule is still what runs in normal usage)."""

import requests
from openai import RateLimitError
from tenacity import wait_fixed

from utils.retry import http_retry, llm_retry


def _run_without_waiting(decorated_func):
    fast_retrying = decorated_func.retry.copy(wait=wait_fixed(0))
    return fast_retrying(decorated_func.__wrapped__)


def test_http_retry_recovers_after_transient_failures():
    calls = {"n": 0}

    @http_retry
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise requests.exceptions.ConnectionError("transient network error")
        return "ok"

    assert _run_without_waiting(flaky) == "ok"
    assert calls["n"] == 3


def test_http_retry_gives_up_after_stop_limit():
    calls = {"n": 0}

    @http_retry
    def always_fails():
        calls["n"] += 1
        raise requests.exceptions.ConnectionError("still down")

    try:
        _run_without_waiting(always_fails)
        assert False, "expected ConnectionError to propagate after retries exhausted"
    except requests.exceptions.ConnectionError:
        pass

    assert calls["n"] == 3  # stop_after_attempt(3)


def test_http_retry_does_not_retry_non_network_errors():
    calls = {"n": 0}

    @http_retry
    def bad_input():
        calls["n"] += 1
        raise ValueError("not a network error")

    try:
        _run_without_waiting(bad_input)
        assert False, "expected ValueError to propagate immediately, without retry"
    except ValueError:
        pass

    assert calls["n"] == 1  # no retry for non-network exceptions


def test_llm_retry_recovers_from_rate_limit():
    calls = {"n": 0}

    class _FakeResponse:
        status_code = 429
        headers = {}
        request = None

    @llm_retry
    def flaky_llm_call():
        calls["n"] += 1
        if calls["n"] < 2:
            raise RateLimitError("rate limited", response=_FakeResponse(), body=None)
        return "ok"

    assert _run_without_waiting(flaky_llm_call) == "ok"
    assert calls["n"] == 2
