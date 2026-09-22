import datetime
from data_sources.market_data import fetch_market_data
from utils.llm import ask_llm
from utils.belief import build_belief_vector
from utils.specialist_response import request_specialist_response
from utils.penalties import recency_weight_from_iso_timestamp
from utils.prompts import MARKET_AGENT_PROMPT
from utils.sanitize import strip_instruction_patterns


def run(data=None, reference_time=None):

    market = data if data is not None else fetch_market_data()
    summary = market["summary_text"]

    prompt = MARKET_AGENT_PROMPT.format(summary=strip_instruction_patterns(summary))
    if reference_time is not None:
        prompt = f"Dự báo hướng giá BTC trong 24 giờ sau {reference_time.isoformat()}. Chỉ sử dụng bằng chứng được cung cấp, không dùng kiến thức về diễn biến sau mốc dự báo.\n" + prompt

    parsed = request_specialist_response(prompt, agent_name="market", ask=ask_llm)

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
            "timestamp": market["fetched_at"] if reference_time is not None else datetime.date.today().isoformat()
        }
    }

    return output
