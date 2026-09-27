import json
from unittest.mock import Mock, patch

import pytest

from agents import sentiment_agent
from utils.grounding import GroundingError
from utils.llm import LLMAPIError
from utils.specialist_response import request_specialist_response


SNAPSHOT = {
    "fetched_at": "2022-01-26T00:00:00+00:00",
    "fear_greed": {"value": 12},
    "upcoming_events": [
        {"title": "Overnight Rate", "forecast": "0.25%", "previous": "0.25%"},
        {"title": "Federal Funds Rate", "forecast": "<0.25%", "previous": "<0.25%"},
    ],
    "summary_text": "Fear & Greed: 12. Forecast/Previous: BOC 0.25%/0.25%; Fed <0.25%/<0.25%.",
}
WRONG = {"signal": "SELL", "confidence": 0.68,
         "logic_path": "BOC và FOMC có dự báo lãi suất thắt chặt hơn, tạo áp lực giảm lên BTC."}
FIXED = {"signal": "NEUTRAL", "confidence": 0.3,
         "logic_path": "Forecast lãi suất bằng Previous; chưa có bằng chứng về thắt chặt hơn."}


def verdict(value="supported", reason="Khớp nguồn"):
    return json.dumps({"checks": [{"claim_index": 0, "verdict": value, "reason": reason}]})


def test_unchanged_rates_rejection_regenerates_entire_decision_before_belief_vector():
    """Replay the failure shape with controlled reviewer output, not a live quality eval."""
    reason = "Forecast bằng Previous không hỗ trợ khẳng định thắt chặt hơn."
    with patch.object(sentiment_agent, "ask_llm", side_effect=[
        json.dumps(WRONG), verdict("unsupported", reason), json.dumps(FIXED), verdict(),
    ]) as ask:
        output = sentiment_agent.run(data=SNAPSHOT)
    assert output["signal"] == "NEUTRAL"
    assert output["confidence"] == 0.3
    assert output["belief_vector"] == {"direction": 0, "strength": 0.3}
    audit = output["specialist_grounding"]
    assert audit["status"] == "accepted"
    assert audit["attempts"][0]["candidate"]["signal"] == "SELL"
    assert audit["attempts"][0]["checks"][0]["verdict"] == "unsupported"
    review_context = json.loads(ask.call_args_list[1].args[0])
    assert review_context["snapshot"] == SNAPSHOT
    assert review_context["candidate"] == WRONG
    assert reason in ask.call_args_list[2].args[0]
    assert [c.kwargs["agent_name"] for c in ask.call_args_list] == ["sentiment", "grounding"] * 2


def test_repeated_unsupported_claim_is_error_not_neutral_or_old_prediction():
    ask = Mock(side_effect=[json.dumps(WRONG), verdict("unsupported", "No tightening evidence")] * 2)
    with pytest.raises(GroundingError) as error:
        request_specialist_response("original prompt", agent_name="sentiment", ask=ask, evidence=SNAPSHOT)
    assert error.value.audit["status"] == "rejected"
    assert len(error.value.audit["attempts"]) == 2
    assert ask.call_count == 4


@pytest.mark.parametrize("bad_review", [
    '{"checks":[]}', '{"checks":[{"claim_index":0,"verdict":"supported"}]}', 'invalid JSON',
])
def test_malformed_review_is_asked_again_once_and_never_approves(bad_review):
    ask = Mock(side_effect=[json.dumps(FIXED), bad_review, bad_review])
    with pytest.raises(GroundingError) as error:
        request_specialist_response("prompt", agent_name="sentiment", ask=ask, evidence=SNAPSHOT)
    audit = error.value.audit
    assert audit["attempts"][0]["stage"] == "review"
    assert (audit["status"], audit["reason"]) == ("json_invalid", "review_json")
    assert ask.call_count == 3


def test_second_review_after_malformed_one_can_decide():
    ask = Mock(side_effect=[json.dumps(FIXED), "invalid JSON", verdict()])
    output = request_specialist_response("prompt", agent_name="sentiment", ask=ask, evidence=SNAPSHOT)
    assert output["specialist_grounding"]["status"] == "accepted"


def test_reviewer_api_failure_is_reported_as_api_error_not_rejection():
    ask = Mock(side_effect=[json.dumps(FIXED), LLMAPIError("rate_limit", "429")])
    with pytest.raises(LLMAPIError):
        request_specialist_response("prompt", agent_name="sentiment", ask=ask, evidence=SNAPSHOT)


def test_factors_and_news_outside_metric_catalog_reach_reviewer_without_truncation():
    snapshot = {"summary_text": "x" * 500 + "\nSàn X thông báo bảo trì rút tiền."}
    payload = {**FIXED, "sentiment_factors": [{"factor": "Sàn X bảo trì rút tiền", "impact": "neutral"}]}
    ask = Mock(side_effect=[json.dumps(payload), verdict()])
    result = request_specialist_response("prompt", agent_name="sentiment", ask=ask, evidence=snapshot)
    context = json.loads(ask.call_args_list[1].args[0])
    assert context["snapshot"] == snapshot
    assert context["candidate"]["sentiment_factors"] == payload["sentiment_factors"]
    assert result["specialist_grounding"]["status"] == "accepted"


def test_missing_snapshot_is_rejected_before_calling_llm():
    ask = Mock()
    with pytest.raises(ValueError, match="original snapshot"):
        request_specialist_response("prompt", agent_name="sentiment", ask=ask, evidence={})
    ask.assert_not_called()
