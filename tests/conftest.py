import datetime

import pytest

TODAY = datetime.date.today().isoformat()


def _agent_output(agent_id, signal, confidence, direction, entropy, redundancy, recency=1.0, timestamp=None, content="evidence text"):
    timestamp = timestamp or TODAY
    return {
        "agent_id": agent_id,
        "signal": signal,
        "confidence": confidence,
        "belief_vector": {"direction": direction, "strength": confidence},
        "evidence_chunks": [{"id": f"{agent_id}_chunk_0", "content": content, "metadata": {}}],
        "logic_path": {"steps": [f"{agent_id} reasoning step"]},
        "metadata": {
            "source_type": "test",
            "entropy": entropy,
            "redundancy_score": redundancy,
            "recency_weight": recency,
            "timestamp": timestamp,
        },
    }


@pytest.fixture
def sample_agents_output():
    """Three specialist outputs in mild, realistic disagreement (not extreme)."""
    return [
        _agent_output("Financial_Agent", "BUY", 0.78, 1, entropy=0.15, redundancy=0.2),
        _agent_output("Market_Agent", "SELL", 0.65, -1, entropy=0.25, redundancy=0.05),
        _agent_output("Sentiment_Agent", "NEUTRAL", 0.40, 0, entropy=0.65, redundancy=0.55),
    ]


@pytest.fixture
def consensus_agents_output():
    """All three agents agree — should yield ~zero conflict."""
    return [
        _agent_output("Financial_Agent", "BUY", 0.8, 1, entropy=0.1, redundancy=0.1),
        _agent_output("Market_Agent", "BUY", 0.75, 1, entropy=0.1, redundancy=0.1),
        _agent_output("Sentiment_Agent", "BUY", 0.7, 1, entropy=0.1, redundancy=0.1),
    ]


@pytest.fixture
def extreme_conflict_output():
    """Sharp BUY vs SELL split with a wide entropy/recency spread — should trip every classifier rule."""
    return [
        _agent_output("agent1", "BUY", 0.9, 1, entropy=0.05, redundancy=0.05),
        _agent_output("agent2", "SELL", 0.9, -1, entropy=0.9, redundancy=0.9),
    ]


@pytest.fixture
def single_agent_output():
    return [_agent_output("Solo_Agent", "BUY", 0.8, 1, entropy=0.1, redundancy=0.1)]
