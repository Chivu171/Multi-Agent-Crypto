import json
from unittest.mock import patch

import pytest

from agents import financial_agent, market_agent, sentiment_agent

VALID_LLM_RESPONSE = json.dumps({
    "signal": "BUY",
    "confidence": 0.72,
    "logic_path": {"steps": ["point one", "point two", "point three"]},
})

FAKE_ONCHAIN_DATA = {
    "fetched_at": "2026-01-01T00:00:00+00:00",
    "summary_text": "On-chain snapshot...",
    "metrics": {
        "hash_rate": {"value": 900.0, "pct_change_1d": 5.0},
        "miners_revenue_usd": {"value": 100.0, "pct_change_1d": -3.0},
        "n_transactions": {"value": 500.0, "pct_change_1d": 0.0},
        "tx_volume_usd": {"value": 1000.0, "pct_change_1d": 2.0},
    },
}

FAKE_MARKET_DATA = {
    "fetched_at": "2026-01-01T00:00:00+00:00",
    "summary_text": "Market snapshot...",
    "rsi14": 72.5,
}

FAKE_SENTIMENT_DATA = {
    "fetched_at": "2026-01-01T00:00:00+00:00",
    "summary_text": "Sentiment snapshot...",
    "fear_greed": {"value": 80, "classification": "Extreme Greed"},
}


def _assert_common_output_shape(output, expected_agent_id):
    assert output["agent_id"] == expected_agent_id
    assert output["signal"] == "BUY"
    assert output["confidence"] == 0.72
    assert output["belief_vector"] == {"direction": 1, "strength": 0.72}
    assert len(output["evidence_chunks"]) == 1
    assert 0.0 <= output["metadata"]["entropy"] <= 1.0
    assert 0.0 <= output["metadata"]["recency_weight"] <= 1.0


def test_financial_agent_run_uses_onchain_fetcher():
    with patch("agents.financial_agent.fetch_onchain_data", return_value=FAKE_ONCHAIN_DATA), \
         patch("agents.financial_agent.ask_llm", return_value=VALID_LLM_RESPONSE):
        output = financial_agent.run()

    _assert_common_output_shape(output, "Financial_Agent")
    # avg(|5|, |-3|, |0|, |2|) / 30 = 2.5 / 30
    assert output["metadata"]["entropy"] == pytest.approx(2.5 / 30, abs=1e-3)


def test_market_agent_run_uses_market_fetcher():
    with patch("agents.market_agent.fetch_market_data", return_value=FAKE_MARKET_DATA), \
         patch("agents.market_agent.ask_llm", return_value=VALID_LLM_RESPONSE):
        output = market_agent.run()

    _assert_common_output_shape(output, "Market_Agent")
    # RSI 72.5 -> entropy = 1 - |72.5-50|/50 = 1 - 0.45 = 0.55
    assert output["metadata"]["entropy"] == pytest.approx(0.55, abs=1e-3)


def test_sentiment_agent_run_uses_sentiment_fetcher():
    with patch("agents.sentiment_agent.fetch_sentiment_data", return_value=FAKE_SENTIMENT_DATA), \
         patch("agents.sentiment_agent.ask_llm", return_value=VALID_LLM_RESPONSE):
        output = sentiment_agent.run()

    _assert_common_output_shape(output, "Sentiment_Agent")
    # F&G 80 -> entropy = 1 - |80-50|/50 = 1 - 0.6 = 0.4
    assert output["metadata"]["entropy"] == pytest.approx(0.4, abs=1e-3)


def test_run_recovers_json_wrapped_in_markdown_fence():
    """LLMs commonly wrap JSON in ```json fences — the agent must still parse it."""
    fenced = "```json\n" + VALID_LLM_RESPONSE + "\n```"
    with patch("agents.financial_agent.fetch_onchain_data", return_value=FAKE_ONCHAIN_DATA), \
         patch("agents.financial_agent.ask_llm", return_value=fenced):
        output = financial_agent.run()
    assert output["signal"] == "BUY"


def test_run_raises_value_error_on_unrecoverable_llm_output():
    with patch("agents.financial_agent.fetch_onchain_data", return_value=FAKE_ONCHAIN_DATA), \
         patch("agents.financial_agent.ask_llm", return_value="not valid json at all"):
        with pytest.raises(ValueError):
            financial_agent.run()


def test_financial_agent_propagates_fetcher_failure():
    """If the data source is unreachable and has no cache, the agent must not
    silently fabricate on-chain data — the exception should surface to main.py's
    per-agent try/except."""
    with patch("agents.financial_agent.fetch_onchain_data", side_effect=RuntimeError("no data available")):
        with pytest.raises(RuntimeError):
            financial_agent.run()
