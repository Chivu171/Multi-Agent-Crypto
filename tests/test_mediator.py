import datetime

from agents.mediator_agent import MediatorAgent, run_mediator


def test_aggregate_returns_final_score_and_details(sample_agents_output):
    mediator = MediatorAgent()
    result = mediator.aggregate(sample_agents_output)

    assert "S_final" in result
    assert isinstance(result["S_final"], float)
    assert len(result["details"]) == len(sample_agents_output)
    for detail in result["details"]:
        assert set(detail) == {"agent_id", "direction", "strength", "weight", "contribution"}


def test_aggregate_all_buy_gives_positive_score(consensus_agents_output):
    mediator = MediatorAgent()
    result = mediator.aggregate(consensus_agents_output)
    assert result["S_final"] > 0


def test_older_evidence_gets_lower_weight():
    mediator = MediatorAgent(gamma=1e-5)
    base_meta = {"entropy": 0.1, "redundancy_score": 0.1, "recency_weight": 1.0}

    today = datetime.date.today().isoformat()
    old_weight = mediator._compute_weight({**base_meta, "timestamp": "2020-01-01"})
    new_weight = mediator._compute_weight({**base_meta, "timestamp": today})

    assert old_weight < new_weight


def test_missing_metadata_falls_back_to_defaults():
    mediator = MediatorAgent()
    weight = mediator._compute_weight({})
    assert weight >= 0.0


def test_run_mediator_wrapper_matches_class(sample_agents_output):
    assert run_mediator(sample_agents_output) == MediatorAgent().aggregate(sample_agents_output)
