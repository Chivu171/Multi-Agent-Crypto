import json
from copy import deepcopy
import datetime as dt
from unittest.mock import patch

from scripts.evaluate_direction import adapter, score
from scripts.evaluate_direction import select_snapshots
from scripts.evaluate_direction import load_cached_completion
import pytest
from agents import financial_agent, market_agent, sentiment_agent


def cached_response(tier="on_demand"):
    return {"id": "groq-fixture", "created": 1, "model": "fixture-model",
            "object": "chat.completion", "service_tier": tier,
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": '{"checks": []}'}}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 5, "total_tokens": 9}}


def test_groq_cache_metadata_does_not_break_replay_or_mutate_provider_record():
    from openai.types.chat import ChatCompletion
    payload = cached_response()
    original = deepcopy(payload)
    with pytest.raises(ValueError, match="service_tier"):
        ChatCompletion.model_validate(payload)  # reproduces the former failure
    response = load_cached_completion(payload)
    assert response.choices[0].message.content == payload["choices"][0]["message"]["content"]
    assert response.choices[0].finish_reason == "stop"
    assert response.usage.total_tokens == 9
    assert response.service_tier is None
    assert payload == original


def test_cache_adapter_preserves_supported_tier_and_still_validates_content():
    assert load_cached_completion(cached_response("default")).service_tier == "default"
    payload = cached_response()
    payload["choices"][0]["message"] = {"role": "not-a-role", "content": "invalid"}
    with pytest.raises(ValueError):
        load_cached_completion(payload)
    with pytest.raises(ValueError, match="service_tier"):
        load_cached_completion(cached_response("unexpected-tier"))


def test_directional_score_excludes_neutral_and_failures():
    predictions = [
        {"sample_id": "a", "status": "ok", "signal": "BUY"},
        {"sample_id": "b", "status": "ok", "signal": "SELL"},
        {"sample_id": "c", "status": "ok", "signal": "NEUTRAL"},
        {"sample_id": "d", "status": "error", "signal": "BUY"},
        {"sample_id": "e", "status": "ok", "signal": "SELL"},
    ]
    labels = [{"sample_id": name, "return_24h": ret} for name, ret in zip("abcde", [.005, .02, -.1, .1, 0])]
    summary, rows = score(predictions, labels)
    assert summary["directional_predictions"] == 3
    assert summary["correct"] == 1  # BUY +0.5% is right direction even though three-class label is neutral
    assert summary["directional_win_rate"] == 1/3
    assert summary["coverage_over_requested"] == 3/5
    assert summary["coverage_over_successful"] == 3/4
    assert summary["neutral_days"] == 1
    assert rows[-1]["correct_direction"] is False


def test_no_predictions_is_undefined_not_zero_win_rate():
    summary, _ = score([{"sample_id": "a", "status": "error"}], [{"sample_id": "a", "return_24h": 1}])
    assert summary["directional_win_rate"] is None
    assert summary["successful_days"] == 0


def test_smoke_selection_preserves_dataset_order_and_rejects_unknown_or_duplicate_ids():
    snapshots = [{"sample_id": d} for d in ("2022-01-12", "2022-01-20", "2022-01-22")]
    assert select_snapshots(snapshots, ["2022-01-22", "2022-01-12"]) == [snapshots[0], snapshots[2]]
    for ids in (["2022-02-01"], ["2022-01-12", "2022-01-12"], []):
        with pytest.raises(ValueError):
            select_snapshots(snapshots, ids)


def test_injected_historical_sources_do_not_call_live_fetchers():
    ref = dt.datetime(2022, 1, 1, tzinfo=dt.timezone.utc)
    stamp = "2021-12-30T00:00:00+00:00"
    payloads = [
        {"fetched_at": stamp, "summary_text": "historical", "metrics": {"hash": {"pct_change_1d": 2}}},
        {"fetched_at": stamp, "summary_text": "historical", "rsi14": 40},
        {"fetched_at": stamp, "summary_text": "historical", "fear_greed": {"value": 28}},
    ]
    response = '{"signal":"BUY","confidence":0.6,"logic_path":"observed evidence"}'
    def reviewed_response(prompt, *, agent_name, **kwargs):
        if agent_name == "grounding":
            return json.dumps({"checks": [{"claim_index": 0, "verdict": "supported", "reason": "Fixture accepted"}]})
        return response
    for module, fetch, data in zip((financial_agent, market_agent, sentiment_agent),
                                   ("fetch_onchain_data", "fetch_market_data", "fetch_sentiment_data"), payloads):
        with patch.object(module, fetch, side_effect=AssertionError("must not call live source")), patch.object(module, "ask_llm", side_effect=reviewed_response) as llm:
            output = module.run(data=data, reference_time=ref)
            assert output["metadata"]["timestamp"] == stamp
            assert "24 giờ" in llm.call_args_list[0].args[0]
            assert ref.isoformat() in llm.call_args_list[0].args[0]
