import datetime as dt
from unittest.mock import patch

from scripts.evaluate_direction import adapter, score
from agents import financial_agent, market_agent, sentiment_agent


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


def test_injected_historical_sources_do_not_call_live_fetchers():
    ref = dt.datetime(2022, 1, 1, tzinfo=dt.timezone.utc)
    stamp = "2021-12-30T00:00:00+00:00"
    payloads = [
        {"fetched_at": stamp, "summary_text": "historical", "metrics": {"hash": {"pct_change_1d": 2}}},
        {"fetched_at": stamp, "summary_text": "historical", "rsi14": 40},
        {"fetched_at": stamp, "summary_text": "historical", "fear_greed": {"value": 28}},
    ]
    response = '{"signal":"BUY","confidence":0.6,"logic_path":"observed evidence"}'
    for module, fetch, data in zip((financial_agent, market_agent, sentiment_agent),
                                   ("fetch_onchain_data", "fetch_market_data", "fetch_sentiment_data"), payloads):
        with patch.object(module, fetch, side_effect=AssertionError("must not call live source")), patch.object(module, "ask_llm", return_value=response) as llm:
            output = module.run(data=data, reference_time=ref)
            assert output["metadata"]["timestamp"] == stamp
            assert "24 giờ" in llm.call_args.args[0]
            assert ref.isoformat() in llm.call_args.args[0]
