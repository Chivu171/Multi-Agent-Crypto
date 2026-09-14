import datetime
from data_sources.sentiment_data import fetch_sentiment_data
from utils.llm import ask_llm
from utils.belief import build_belief_vector
from utils.parsing import parse_json_response
from utils.penalties import recency_weight_from_iso_timestamp
from utils.prompts import SENTIMENT_AGENT_PROMPT
from utils.sanitize import strip_instruction_patterns


def run():

    sentiment = fetch_sentiment_data()
    text = sentiment["summary_text"]

    prompt = SENTIMENT_AGENT_PROMPT.format(text=strip_instruction_patterns(text))

    raw_response = ask_llm(prompt, agent_name="sentiment")

    parsed = parse_json_response(raw_response)

    signal = parsed["signal"]
    confidence = float(parsed["confidence"])

    # Entropy proxy: Fear&Greed near 50 = ambiguous/high entropy, near 0/100 = decisive/low entropy.
    fg_value = sentiment["fear_greed"]["value"]
    entropy = 1.0 - abs(fg_value - 50.0) / 50.0

    output = {
        "agent_id": "Sentiment_Agent",

        "signal": signal,

        "confidence": confidence,

        "belief_vector": build_belief_vector(
            signal,
            confidence
        ),

        "evidence_chunks": [
            {
                "id": "sentiment_chunk_001",

                "content": text,

                "metadata": {
                    "source": "Alternative.me + ForexFactory calendar",
                    "timestamp": sentiment["fetched_at"]
                }
            }
        ],

        "logic_path": parsed["logic_path"],

        "metadata": {
            "source_type": "social_media",
            "entropy": round(entropy, 3),  # derived from Fear&Greed distance to the neutral midpoint (50)
            "redundancy_score": 0.1,  # single canonical API pair, no cross-outlet duplication
            "recency_weight": round(recency_weight_from_iso_timestamp(sentiment["fetched_at"]), 3),
            "timestamp": datetime.date.today().isoformat()
        }
    }

    return output
