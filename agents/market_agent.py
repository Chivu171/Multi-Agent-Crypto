import json
import datetime
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
                    "timestamp": datetime.date.today().isoformat()
                }
            }
        ],

        "logic_path": parsed["logic_path"],

        "metadata": {
            "source_type": "market_data",
            "entropy": 0.25,        # EMA/RSI deterministic nhưng 23-signal composite có 22% vs 61% split
            "redundancy_score": 0.05, # price/ETF flow nhất quán giữa CoinGlass/Bloomberg/Farside
            "recency_weight": 0.98,  # real-time data, ETF flow T+1 — nguồn tin cậy nhất về timing
            "timestamp": datetime.date.today().isoformat()
        }
    }

    return output