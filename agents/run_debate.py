from typing import List, Dict, Any
from agents.debate_agent import DebateAgent


def run_debate(agents_output: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convenient wrapper to execute the deterministic debate.
    Uses the default settings (3 rounds, alpha=0.5, equal weighting).
    """
    debate = DebateAgent(rounds=3, alpha=0.5)
    return debate.run_debate(agents_output)
