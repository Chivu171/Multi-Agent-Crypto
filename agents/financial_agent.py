import datetime
from data_sources.onchain_data import fetch_onchain_data
from utils.llm import ask_llm
from utils.belief import build_belief_vector
from utils.specialist_response import request_specialist_response
from utils.penalties import recency_weight_from_iso_timestamp
from utils.prompts import FINANCIAL_AGENT_PROMPT
from utils.sanitize import strip_instruction_patterns


def run(data=None, reference_time=None):

    onchain = data if data is not None else fetch_onchain_data()
    text = onchain["summary_text"]

    prompt = FINANCIAL_AGENT_PROMPT.format(text=strip_instruction_patterns(text))
    if reference_time is not None:
        prompt = f"Dự báo hướng giá BTC trong 24 giờ sau {reference_time.isoformat()}. Chỉ sử dụng bằng chứng được cung cấp, không dùng kiến thức về diễn biến sau mốc dự báo.\n" + prompt

    parsed = request_specialist_response(prompt, agent_name="financial", ask=ask_llm)

    signal = parsed["signal"]
    confidence = float(parsed["confidence"])

    # Entropy proxy: how noisy/dispersed the on-chain metrics are right now —
    # larger day-over-day swings across metrics mean less certain signal.
    pct_changes = [abs(m["pct_change_1d"]) for m in onchain["metrics"].values()]
    entropy = min(max((sum(pct_changes) / len(pct_changes)) / 30.0, 0.0), 1.0)

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

                "content": text,

                "metadata": {
                    "source": "blockchain.info Charts API",
                    "page": 1,
                    "timestamp": onchain["fetched_at"]
                }
            }
        ],

        "logic_path": parsed["logic_path"],

        "metadata": {
            "source_type": "financial_report",
            "entropy": round(entropy, 3),  # avg |% change| across hash-rate/miner-revenue/tx-count/tx-volume
            "redundancy_score": 0.1,  # single canonical API source, no cross-outlet duplication
            "recency_weight": round(recency_weight_from_iso_timestamp(onchain["fetched_at"]), 3),
            "timestamp": onchain["fetched_at"] if reference_time is not None else datetime.date.today().isoformat()
        }
    }

    return output
