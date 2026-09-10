from unittest.mock import patch

from agents.validator_agent import ValidatorAgent


def test_calculate_conflict_core_returns_bounded_values(sample_agents_output):
    validator = ValidatorAgent(alpha=0.6, threshold=0.4, use_llm=False)
    conflict_score, mean_kl, variance = validator.calculate_conflict_core(sample_agents_output)

    assert isinstance(conflict_score, float)
    assert mean_kl >= 0.0
    assert variance >= 0.0


def test_single_agent_has_zero_conflict(single_agent_output):
    validator = ValidatorAgent()
    conflict_score, mean_kl, variance = validator.calculate_conflict_core(single_agent_output)
    assert mean_kl == 0.0
    assert variance == 0.0
    assert conflict_score == 0.0


def test_consensus_has_lower_conflict_than_disagreement(consensus_agents_output, extreme_conflict_output):
    validator = ValidatorAgent()
    consensus_score, _, _ = validator.calculate_conflict_core(consensus_agents_output)
    conflict_score, _, _ = validator.calculate_conflict_core(extreme_conflict_output)
    assert consensus_score < conflict_score


def test_classify_conflict_below_015_is_no_conflict():
    validator = ValidatorAgent()
    assert validator.classify_conflict([], 0.1) == ["No Conflict"]


def test_classify_conflict_detects_signal_conflict(extreme_conflict_output):
    validator = ValidatorAgent()
    categories = validator.classify_conflict(extreme_conflict_output, conflict_score=0.5)
    assert "Signal Conflict" in categories


def test_classify_conflict_detects_temporal_and_reliability(extreme_conflict_output):
    validator = ValidatorAgent()
    categories = validator.classify_conflict(extreme_conflict_output, conflict_score=0.5)
    # recency_weight is now intrinsic (no time decay), so Temporal Conflict
    # is no longer triggered by recency weight spread alone. We still expect
    # signal and reliability conflicts from the extreme fixture.
    assert "Signal Conflict" in categories
    assert "Reliability Conflict" in categories


def test_evaluate_pipeline_no_conflict_skips_debate(consensus_agents_output):
    validator = ValidatorAgent(threshold=0.8, use_llm=False)
    result = validator.evaluate_pipeline(consensus_agents_output)

    assert result["conflict_detected"] is False
    assert result["debate_updated_outputs"] is None
    assert result["root_cause_analysis"] == "N/A - System in state of consensus."


@patch("agents.debate_agent.ask_llm")
def test_evaluate_pipeline_conflict_triggers_debate(mock_ask_llm, extreme_conflict_output):
    mock_ask_llm.return_value = '{"steps": ["a", "b", "c"]}'

    validator = ValidatorAgent(threshold=0.1, use_llm=False)
    result = validator.evaluate_pipeline(extreme_conflict_output)

    assert result["conflict_detected"] is True
    assert result["trigger_debate_module"] is True
    assert result["debate_updated_outputs"] is not None
    assert len(result["debate_updated_outputs"]) == len(extreme_conflict_output)
    assert mock_ask_llm.called


def test_evaluate_pipeline_rca_fallback_without_llm(extreme_conflict_output):
    """use_llm=False must not call the network — it returns a deterministic fallback string."""
    with patch("agents.debate_agent.ask_llm", return_value='{"steps": ["a"]}'):
        validator = ValidatorAgent(threshold=0.1, use_llm=False)
        result = validator.evaluate_pipeline(extreme_conflict_output)

    assert "RCA Triggered" in result["root_cause_analysis"]
