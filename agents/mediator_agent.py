# agents/mediator_agent.py

r"""Mediator Agent

Tích hợp công thức tổng hợp cuối cùng:
    S_final = \sum_{i=1}^{3} (d_i * s_i * \omega_i)
Trong đó:
    d_i   – hướng (direction) từ belief_vector (‑1, 0, 1)
    s_i   – strength (confidence) từ belief_vector
    \omega_i   – trọng số đã được điều chỉnh bằng các hàm phạt:
        * entropy_penalty
        * redundancy_penalty
        * time_decay_penalty

Trọng số cuối cùng được tính bằng hàm `combined_weight` trong
`utils/penalties.py`.
"""

import json
import datetime
from typing import List, Dict, Any

from utils.penalties import combined_weight


def _parse_timestamp(ts: str) -> datetime.datetime:
    """Chuyển chuỗi timestamp (ISO 8601) thành datetime.
    Nếu không phân tích được, trả về thời điểm hiện tại.
    """
    try:
        return datetime.datetime.fromisoformat(ts)
    except Exception:
        # Fallback: assume YYYY‑MM‑DD format
        try:
            return datetime.datetime.strptime(ts, "%Y-%m-%d")
        except Exception:
            return datetime.datetime.utcnow()


class MediatorAgent:
    """Agent hợp nhất thông tin từ các Specialist Agents.

    - Áp dụng các penalty để giảm trọng số nguồn dữ liệu.
    - Tính thời gian trì hoãn (Δt) dựa trên `metadata['timestamp']`.
    - Trả về giá trị S_final và chi tiết từng nguồn.
    """

    def __init__(self, gamma: float = 1e-5):
        self.gamma = gamma  # Tham số cho hàm time_decay_penalty

    def _compute_weight(self, meta: Dict[str, Any]) -> float:
        r"""Tính \omega_i dựa trên metadata của một agent.

        Metadata cần có các trường:
            - entropy (float)
            - redundancy_score (float)
            - timestamp (str) – thời gian tạo evidence
            - recency_weight (float) – trọng số cơ bản (base_weight)
        """
        entropy = float(meta.get("entropy", 0.0))
        redundancy = float(meta.get("redundancy_score", 0.0))
        base_weight = float(meta.get("recency_weight", 1.0))
        ts_str = meta.get("timestamp", "")
        delta_seconds = (datetime.datetime.utcnow() - _parse_timestamp(ts_str)).total_seconds()
        delta_seconds = max(delta_seconds, 0.0)
        return combined_weight(base_weight, entropy, redundancy, delta_seconds, gamma=self.gamma)

    def aggregate(self, agents_output: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Thực hiện hợp nhất và trả về kết quả.

        Returns
        -------
        dict
            {
                "S_final": float,
                "details": [
                    {
                        "agent_id": str,
                        "direction": int,
                        "strength": float,
                        "weight": float,
                        "contribution": float
                    }, ...
                ]
            }
        """
        total = 0.0
        details = []
        for out in agents_output:
            bv = out.get("belief_vector", {})
            direction = int(bv.get("direction", 0))
            strength = float(bv.get("strength", 0.0))
            meta = out.get("metadata", {})
            weight = self._compute_weight(meta)
            contribution = direction * strength * weight
            total += contribution
            details.append(
                {
                    "agent_id": out.get("agent_id", "unknown"),
                    "direction": direction,
                    "strength": strength,
                    "weight": round(weight, 6),
                    "contribution": round(contribution, 6),
                }
            )
        return {"S_final": round(total, 6), "details": details}


def run_mediator(agents_output: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Convenient wrapper used by pipelines.
    Instantiates `MediatorAgent` with default gamma and returns the aggregation.
    """
    mediator = MediatorAgent()
    return mediator.aggregate(agents_output)
