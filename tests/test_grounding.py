import json
from copy import deepcopy
from unittest.mock import Mock, patch

import pytest

from agents.debate_agent import DebateAgent
from agents.validator_agent import ValidatorAgent
from utils.grounding import (
    GroundingError, build_evidence_registry, request_grounded_claims,
    validate_citations, validate_review,
)


def claim(text="Funding dương 0.0100%", quote="Funding rate: 0.0100%", evidence_id="E001", kind="fact"):
    return {"claims": [{"type": kind, "text": text, "citations": [{"evidence_id": evidence_id, "quote": quote}]}]}


def review(verdict="supported", reason="Khớp dữ liệu nguồn"):
    return {"checks": [{"claim_index": 0, "verdict": verdict, "reason": reason}]}


@pytest.fixture
def evidence():
    return [{"evidence_id": "E001", "agent_id": "Market_Agent", "content": "Funding rate: 0.0100%", "metadata": {"source": "test"}}]


def test_registry_retains_own_other_evidence_metadata_and_text_beyond_200_chars(sample_agents_output):
    sample_agents_output[0]["evidence_chunks"][0]["content"] = "x"*500 + " important tail"
    sample_agents_output[0]["evidence_chunks"][0]["metadata"] = {"source": "origin", "timestamp": "2026-09-22"}
    registry = build_evidence_registry(sample_agents_output)
    assert len(registry) == 3
    assert registry[0]["content"].endswith("important tail")
    assert len(registry[0]["content"]) > 500
    assert registry[0]["metadata"]["source"] == "origin"
    assert {e["agent_id"] for e in registry} == {a["agent_id"] for a in sample_agents_output}


@pytest.mark.parametrize("payload", [claim(evidence_id="E999"), claim(quote="Funding rate: -0.0100%"),
    {"claims": [{"type": "fact", "text": "test", "citations": []}]}, {"claims": []}])
def test_fake_missing_citations_rejected_before_review(payload, evidence):
    ask = Mock(return_value=json.dumps(payload))
    with pytest.raises(GroundingError):
        request_grounded_claims("test", evidence, agent_name="debate", ask=ask)
    assert ask.call_count == 2
    assert all(c.kwargs["agent_name"] == "debate" for c in ask.call_args_list)


def test_funding_wrong_sign_with_real_quote_is_not_accepted_on_citation_alone(evidence):
    wrong = claim(text="Funding âm xác nhận áp lực bán")
    ask = Mock(side_effect=[json.dumps(wrong), json.dumps(review("contradicted", "Funding trong nguồn là dương")),
                            json.dumps(claim()), json.dumps(review())])
    claims, audit = request_grounded_claims("test", evidence, agent_name="debate", ask=ask)
    assert claims[0]["text"] == "Funding dương 0.0100%"
    assert audit["status"] == "accepted"
    assert audit["attempts"][0]["checks"][0]["verdict"] == "contradicted"
    assert ask.call_count == 4


@pytest.mark.parametrize("text", ["MVRV cao cảnh báo bán tháo", "ETF dòng tiền ròng dương hỗ trợ sàn"])
def test_unsupported_claim_using_unavailability_quote_is_rejected(text):
    content = "No MVRV or ETF flow data in this snapshot."
    registry = [{"evidence_id": "E001", "content": content}]
    payload = claim(text=text, quote=content)
    ask = Mock(side_effect=[json.dumps(payload), json.dumps(review("unsupported", "Nguồn nói không có dữ liệu"))]*2)
    with pytest.raises(GroundingError) as error:
        request_grounded_claims("test", registry, agent_name="debate", ask=ask)
    assert error.value.audit["status"] == "rejected"
    assert len(error.value.audit["attempts"]) == 2


def test_news_outside_structured_metrics_is_allowed():
    content = "Thông báo của sàn X: tạm dừng rút tiền để bảo trì."
    registry = [{"evidence_id": "E001", "content": content, "metadata": {"source": "news fixture"}}]
    payload = claim(text="Theo thông báo, sàn X tạm dừng rút tiền để bảo trì.", quote=content)
    ask = Mock(side_effect=[json.dumps(payload), json.dumps(review())])
    claims, audit = request_grounded_claims("test", registry, agent_name="validator", ask=ask)
    assert audit["status"] == "accepted"
    assert claims[0]["citations"][0]["quote"] == content


@pytest.mark.parametrize("payload", [{"checks": []}, {"checks": [review()["checks"][0]]*2},
    {"checks": [{"claim_index": 1, "verdict": "supported", "reason": "x"}]},
    {"checks": [{"claim_index": 0, "verdict": "maybe", "reason": "x"}]}])
def test_incomplete_or_invalid_reviewer_cannot_approve(payload):
    with pytest.raises(ValueError):
        validate_review(payload, 1)


def test_reviewer_failure_is_fail_closed(evidence):
    ask = Mock(side_effect=[json.dumps(claim()), RuntimeError("network failed")])
    with pytest.raises(GroundingError) as error:
        request_grounded_claims("test", evidence, agent_name="debate", ask=ask)
    assert error.value.audit["attempts"][0]["stage"] == "review"
    assert ask.call_count == 2


def test_rejected_debate_preserves_entire_decision_state(extreme_conflict_output):
    original = deepcopy(extreme_conflict_output)
    with patch("agents.debate_agent.ask_llm", return_value='{"claims":[]}'):
        out = DebateAgent(rounds=2).run_debate(extreme_conflict_output)
    assert extreme_conflict_output == original
    for before, after in zip(original, out):
        for field in ["signal", "confidence", "belief_vector", "logic_path", "evidence_chunks"]:
            assert after[field] == before[field]
        assert [a["status"] for a in after["debate_audit"]] == ["rejected", "rejected"]


def supported_ask(prompt, *, agent_name, **kwargs):
    if agent_name == "grounding":
        return json.dumps(review())
    context = json.loads(prompt)
    source = context["evidence"][0]
    return json.dumps(claim(text=source["content"], quote=source["content"], evidence_id=source["evidence_id"]))


def test_accepted_debate_has_full_context_and_updates_only_after_review(extreme_conflict_output):
    extreme_conflict_output[0]["evidence_chunks"][0]["content"] = "x"*210 + " own source tail"
    extreme_conflict_output[1]["evidence_chunks"][0]["content"] = "y"*210 + " other source tail"
    with patch("agents.debate_agent.ask_llm", side_effect=supported_ask) as ask:
        output = DebateAgent(rounds=2).run_debate(extreme_conflict_output)
    for call in ask.call_args_list:
        assert "own source tail" in call.args[0]
        assert "other source tail" in call.args[0]
    for before, after in zip(extreme_conflict_output, output):
        assert after["confidence"] < before["confidence"]
        assert after["signal"] == before["signal"]
        assert all(a["status"] == "accepted" for a in after["debate_audit"])
        assert "[E001]" in after["logic_path"]["steps"][0]


def test_rca_passes_full_sources_and_flags_rejection(extreme_conflict_output):
    extreme_conflict_output[0]["evidence_chunks"][0]["content"] = "x"*250 + " last source fact"
    validator = ValidatorAgent()
    with patch("agents.validator_agent.ask_llm", return_value='{"claims":[]}') as ask:
        result = validator.run_root_cause_analysis(extreme_conflict_output, ["Signal Conflict"])
    assert "last source fact" in ask.call_args.args[0]
    assert "chưa có giải thích đạt kiểm tra nguồn" in result
    assert validator.rca_grounding["status"] == "rejected"


def test_full_pipeline_reports_grounding_failures(extreme_conflict_output):
    with patch("agents.validator_agent.ask_llm", return_value='{"claims":[]}'), \
         patch("agents.debate_agent.ask_llm", return_value='{"claims":[]}'):
        report = ValidatorAgent(threshold=.1).evaluate_pipeline(extreme_conflict_output)
    assert report["explanations_valid"] is False
    assert report["debate_status"] == "rejected"
    assert report["conflict_score_after_debate"] == report["conflict_score"]


def test_history_is_not_cut_to_120_characters(extreme_conflict_output):
    extreme_conflict_output[0]["logic_path"] = {"steps": ["x"*200 + " final caveat"]}
    assert "final caveat" in DebateAgent._build_debate_history(1, extreme_conflict_output)
