import json
from utils.llm import ask_llm
from utils.belief import build_belief_vector
from utils.prompts import MARKET_AGENT_PROMPT


def run():

    with open("data/market_data.txt", "r", encoding="utf-8") as f:
        summary = f.read()

    prompt = MARKET_AGENT_PROMPT.format(summary=summary)

    raw_response = ask_llm(prompt, agent_name="market")

    parsed = json.loads(raw_response)

    signal = parsed["signal"]
    confidence = float(parsed["confidence"])

    output = {
        "agent_id": "Market_Agent",

        "signal": signal,

        "confidence": confidence,

        "belief_vector": build_belief_vector(
            signal,
            confidence
        ),

        "evidence_chunks": [
            {
                "id": "market_chunk_001",

                "content": summary,

                "metadata": {
                    "source": "market_data.txt",
                    "timestamp": "2026-05-19"
                }
            }
        ],

        "logic_path": parsed["logic_path"],

        "metadata": {
            "source_type": "market_data",
            "entropy": 0.3,
            "redundancy_score": 0.05,
            "recency_weight": 0.98,
            "timestamp": "2026-05-19"
        }
    }

    return output