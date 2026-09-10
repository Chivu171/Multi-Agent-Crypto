import datetime
from data_sources.market_data import fetch_market_data
from utils.llm import ask_llm
from utils.belief import build_belief_vector
from utils.parsing import parse_json_response
from utils.penalties import recency_weight_from_iso_timestamp
from utils.prompts import MARKET_AGENT_PROMPT


def run():

    market = fetch_market_data()
    summary = market["summary_text"]

    prompt = MARKET_AGENT_PROMPT.format(summary=summary)

    system_prompt = (
        "You are a strict JSON-only API. "
        "Output ONLY a single JSON object starting with { and ending with }. "
        "No thinking, no reasoning, no explanation, no markdown, no extra text."
    )

    raw_response = ask_llm(prompt, agent_name="market", system=system_prompt)

    parsed = parse_json_response(raw_response)

    signal = parsed["signal"]
    confidence = float(parsed["confidence"])

    # Entropy proxy: RSI near 50 = ambiguous/high entropy, RSI near 0/100 = decisive/low entropy.
    entropy = 1.0 - abs(market["rsi14"] - 50.0) / 50.0

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
                    "source": "Binance public API",
                    "timestamp": market["fetched_at"]
                }
            }
        ],

        "logic_path": parsed["logic_path"],

        "metadata": {
            "source_type": "market_data",
            "entropy": round(entropy, 3),  # derived from RSI14 distance to the neutral midpoint (50)
            "redundancy_score": 0.05,  # single canonical exchange API, no cross-outlet duplication
            "recency_weight": round(recency_weight_from_iso_timestamp(market["fetched_at"]), 3),
            "timestamp": datetime.date.today().isoformat()
        }
    }

    return output
