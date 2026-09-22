import datetime
from data_sources.sentiment_data import fetch_sentiment_data
from utils.llm import ask_llm
from utils.belief import build_belief_vector
from utils.specialist_response import request_specialist_response
from utils.penalties import recency_weight_from_iso_timestamp
from utils.prompts import SENTIMENT_AGENT_PROMPT
from utils.sanitize import strip_instruction_patterns


def run(data=None, reference_time=None):

    sentiment = data if data is not None else fetch_sentiment_data()
    text = sentiment["summary_text"]

    prompt = SENTIMENT_AGENT_PROMPT.format(text=strip_instruction_patterns(text))
    if reference_time is not None:
        prompt = f"Dự báo hướng giá BTC trong 24 giờ sau {reference_time.isoformat()}. Chỉ sử dụng bằng chứng được cung cấp, không dùng kiến thức về diễn biến sau mốc dự báo.\n" + prompt

    parsed = request_specialist_response(prompt, agent_name="sentiment", ask=ask_llm)

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
            "timestamp": sentiment["fetched_at"] if reference_time is not None else datetime.date.today().isoformat()
        }
    }

    return output
