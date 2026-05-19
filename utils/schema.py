# utils/schema.py

from typing import TypedDict, List, Dict, Any


SIGNAL_MAP = {
    "BUY": 1,
    "SELL": -1,
    "NEUTRAL": 0
}


class EvidenceChunk(TypedDict):
    id: str
    content: str
    metadata: Dict[str, Any]


class BeliefVector(TypedDict):
    direction: int
    strength: float


class AgentOutput(TypedDict):
    agent_id: str

    signal: str

    confidence: float

    belief_vector: BeliefVector

    evidence_chunks: List[EvidenceChunk]

    logic_path: str

    metadata: Dict[str, Any]


