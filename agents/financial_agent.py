import json
import datetime
from utils.llm import ask_llm
from utils.belief import build_belief_vector
from utils.prompts import FINANCIAL_AGENT_PROMPT


def run():

    with open("data/financial_report.txt", "r", encoding="utf-8") as f:
        text = f.read()

    prompt = FINANCIAL_AGENT_PROMPT.format(text=text)

    raw_response = ask_llm(prompt, agent_name="financial")

    parsed = json.loads(raw_response)

    signal = parsed["signal"]
    confidence = float(parsed["confidence"])

    output = {
        "agent_id": "Financial_Agent",

        "signal": signal,

        "confidence": confidence,

        "belief_vector": build_belief_vector(
            signal,
            confidence
        ),

        "evidence_chunks": [
            {
                "id": "financial_chunk_001",

                "content": text[:300],

                "metadata": {
                    "source": "financial_report.txt",
                    "page": 1,
                    "timestamp": datetime.date.today().isoformat()
                }
            }
        ],

        "logic_path": parsed["logic_path"],

        "metadata": {
            "source_type": "financial_report",
            "entropy": 0.15,        # metrics deterministic (MVRV, SOPR, exchange supply) — ít ambiguity
            "redundancy_score": 0.2, # whale figure từ 6+ outlets nhưng cùng 1 Glassnode source
            "recency_weight": 0.45,  # on-chain aggregate lag 1-24h → Temporal Conflict với market
            "timestamp": datetime.date.today().isoformat()
        }
    }

    return output