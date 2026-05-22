from agents.validator_agent import ValidatorAgent

# Sample agents output list with minimal required fields
agents_output = [
    {
        "agent_id": "agent1",
        "belief_vector": {"direction": 1, "strength": 0.8},
        "confidence": 0.6,
        "signal": "BUY",
        "logic_path": {"step": "analysis"},
        "evidence_chunks": [{"content": "Positive market sentiment"}],
        "metadata": {"recency_weight": 0.2, "redundancy_score": 0.1, "entropy": 0.3}
    },
    {
        "agent_id": "agent2",
        "belief_vector": {"direction": -1, "strength": 0.6},
        "confidence": 0.5,
        "signal": "SELL",
        "logic_path": {"step": "analysis"},
        "evidence_chunks": [{"content": "Negative price movement"}],
        "metadata": {"recency_weight": 0.5, "redundancy_score": 0.2, "entropy": 0.6}
    }
]

validator = ValidatorAgent(alpha=0.6, threshold=0.1, use_llm=False)
result = validator.evaluate_pipeline(agents_output)
print("Result:")
print(result)
