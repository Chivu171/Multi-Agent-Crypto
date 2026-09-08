from unittest.mock import patch

import numpy as np

from agents.debate_agent import (
    DebateAgent,
    _cosine_distance,
    _jaccard_distance,
    _levenshtein_distance,
    _logic_path_distance,
)


def test_cosine_distance_identical_vectors_is_zero():
    v = np.array([1.0, 2.0, 3.0])
    assert _cosine_distance(v, v) == 0.0


def test_cosine_distance_zero_vector_is_max_distance():
    assert _cosine_distance(np.array([0.0, 0.0]), np.array([1.0, 1.0])) == 1.0


def test_jaccard_distance_identical_sets_is_zero():
    chunks = [{"content": "whale accumulation strong"}]
    assert _jaccard_distance(chunks, chunks) == 0.0


def test_jaccard_distance_disjoint_sets_is_one():
    a = [{"content": "alpha beta"}]
    b = [{"content": "gamma delta"}]
    assert _jaccard_distance(a, b) == 1.0


def test_levenshtein_distance_basic():
    assert _levenshtein_distance("kitten", "kitten") == 0
    assert _levenshtein_distance("kitten", "sitting") == 3
    assert _levenshtein_distance("", "abc") == 3


def test_logic_path_distance_identical_is_zero():
    path = {"steps": ["a", "b"]}
    assert _logic_path_distance(path, path) == 0.0


def test_rebuttal_strength_is_normalized(sample_agents_output):
    agent = DebateAgent(rounds=1)
    vectors = agent._prepare_vectors(sample_agents_output)
    strength = agent._rebuttal_strength("Financial_Agent", sample_agents_output, vectors)
    assert 0.0 <= strength <= 1.0


@patch("agents.debate_agent.ask_llm")
def test_run_debate_updates_confidence_and_preserves_agent_count(mock_ask_llm, extreme_conflict_output):
    mock_ask_llm.return_value = '{"steps": ["updated point one", "updated point two"]}'

    agent = DebateAgent(rounds=2, alpha=0.35)
    result = agent.run_debate(extreme_conflict_output)

    assert len(result) == len(extreme_conflict_output)
    assert {o["agent_id"] for o in result} == {o["agent_id"] for o in extreme_conflict_output}
    for out in result:
        assert 0.0 <= out["confidence"] <= 1.0


@patch("agents.debate_agent.ask_llm", side_effect=RuntimeError("LLM unreachable"))
def test_run_debate_keeps_old_logic_path_on_llm_failure(mock_ask_llm, extreme_conflict_output):
    agent = DebateAgent(rounds=1)
    result = agent.run_debate(extreme_conflict_output)

    original_paths = {o["agent_id"]: o["logic_path"] for o in extreme_conflict_output}
    for out in result:
        assert out["logic_path"] == original_paths[out["agent_id"]]
