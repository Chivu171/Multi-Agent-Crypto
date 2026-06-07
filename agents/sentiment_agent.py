import json
import datetime
from utils.llm import ask_llm
from utils.belief import build_belief_vector
from utils.prompts import SENTIMENT_AGENT_PROMPT


def run():

    with open("data/sentiment_news.txt", "r", encoding="utf-8") as f:
        text = f.read()

    prompt = SENTIMENT_AGENT_PROMPT.format(text=text)

    raw_response = ask_llm(prompt, agent_name="sentiment")

    parsed = json.loads(raw_response)

    signal = parsed["signal"]
    confidence = float(parsed["confidence"])

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
                    "source": "sentiment_news.txt",
                    "timestamp": datetime.date.today().isoformat()
                }
            }
        ],

        "logic_path": parsed["logic_path"],

        "metadata": {
            "source_type": "social_media",
            "entropy": 0.65,        # Fear=12 vs contrarian signals + unverified rumor (Strategy sale)
            "redundancy_score": 0.55, # "$3.4B ETF outflow" republished 8+ outlets từ 1 Bloomberg source
            "recency_weight": 0.80,  # tin tức hôm nay nhưng qua biên tập, F&G cập nhật hàng ngày
            "timestamp": datetime.date.today().isoformat()
        }
    }

    return output