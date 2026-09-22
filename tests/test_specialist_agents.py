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


@pytest.mark.parametrize("module,data", [
    (financial_agent, FAKE_ONCHAIN_DATA),
    (market_agent, FAKE_MARKET_DATA),
    (sentiment_agent, FAKE_SENTIMENT_DATA),
])
@pytest.mark.parametrize("raw_signal,expected,direction", [
    ("MUA", "BUY", 1), ("bán", "SELL", -1), ("TRUNG LẬP", "NEUTRAL", 0),
])
def test_translated_signals_are_canonical_before_belief_vector(module, data, raw_signal, expected, direction):
    payload = json.loads(VALID_LLM_RESPONSE)
    payload["signal"] = raw_signal
    with patch.object(module, "ask_llm", return_value=json.dumps(payload)) as ask:
        output = module.run(data=data)
    assert output["signal"] == expected
    assert output["belief_vector"]["direction"] == direction
    assert ask.call_count == 1
    assert "never translate" in ask.call_args.kwargs["system"]


@pytest.mark.parametrize("module,data", [
    (financial_agent, FAKE_ONCHAIN_DATA),
    (market_agent, FAKE_MARKET_DATA),
    (sentiment_agent, FAKE_SENTIMENT_DATA),
])
def test_truncated_json_is_regenerated_once_on_same_evidence(module, data):
    truncated = '```json\n{"signal":"BUY","confidence":0.6,"logic_path":"Giá tăng'
    with patch.object(module, "ask_llm", side_effect=[truncated, VALID_LLM_RESPONSE]) as ask:
        output = module.run(data=data)
    _assert_common_output_shape(output, module.__name__.split(".")[-1].replace("_agent", "").capitalize() + "_Agent")
    assert ask.call_count == 2
    original_prompt, retry_prompt = [call.args[0] for call in ask.call_args_list]
    assert retry_prompt.startswith(original_prompt)


def test_repeated_malformed_output_remains_an_error_not_neutral():
    with patch.object(sentiment_agent, "ask_llm", return_value='{"signal":"BUY"') as ask:
        with pytest.raises(ValueError, match="after 2 attempts"):
            sentiment_agent.run(data=FAKE_SENTIMENT_DATA)
    assert ask.call_count == 2


@pytest.mark.parametrize("updates", [
    {"signal": "MUA HOẶC BÁN"},
    {"confidence": 1.5},
    {"confidence": float("nan")},
    {"confidence": True},
    {"logic_path": ""},
])
def test_invalid_schema_cannot_reach_belief_vector(updates):
    payload = {**json.loads(VALID_LLM_RESPONSE), **updates}
    with patch.object(financial_agent, "ask_llm", return_value=json.dumps(payload)) as ask:
        with pytest.raises(ValueError, match="after 2 attempts"):
            financial_agent.run(data=FAKE_ONCHAIN_DATA)
    assert ask.call_count == 2


def test_provider_truncation_gets_one_shorter_regeneration():
    from utils.llm import IncompleteLLMResponse
    with patch.object(market_agent, "ask_llm", side_effect=[
        IncompleteLLMResponse("finish_reason=length"), VALID_LLM_RESPONSE,
    ]) as ask:
        output = market_agent.run(data=FAKE_MARKET_DATA)
    assert output["signal"] == "BUY"
    assert ask.call_count == 2


def test_api_failure_is_not_retried_as_a_format_error():
    with patch.object(market_agent, "ask_llm", side_effect=RuntimeError("API unavailable")) as ask:
        with pytest.raises(RuntimeError, match="API unavailable"):
            market_agent.run(data=FAKE_MARKET_DATA)
    assert ask.call_count == 1
