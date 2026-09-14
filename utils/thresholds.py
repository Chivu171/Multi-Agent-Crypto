# utils/thresholds.py

"""Các ngưỡng/tham số dùng trong Validator, Debate và quyết định tín hiệu
cuối cùng (Mediator → main.py).

⚠️ CHƯA HIỆU CHỈNH BẰNG THỰC NGHIỆM — toàn bộ giá trị dưới đây là số đặt
tạm dựa trên trực giác lúc thiết kế (giống ngưỡng RSI 30/70 kinh điển),
CHƯA chạy backtest để kiểm chứng có tối ưu cho tín hiệu BTC hay không.
Việc hiệu chỉnh thật sự (thử nhiều giá trị, so accuracy/Sharpe/drawdown)
thuộc phạm vi ĐATN — xem DATN-01 → DATN-04 (docs/LO_TRINH_P3_DATN.md).

Gom về một file duy nhất để minh bạch hoá: người đọc thấy ngay đây là giả
định có chủ đích, không phải số bị giấu rải rác giữa logic nghiệp vụ.
"""

# ---- ValidatorAgent: cân bằng công thức Hybrid Conflict Score ----
DEFAULT_CONFLICT_ALPHA = 0.6
"""Trọng số giữa KL Divergence (học thuật) và Variance (thực nghiệm) trong
conflict_score = alpha * mean_kl + (1 - alpha) * variance."""

DEFAULT_CONFLICT_THRESHOLD = 0.4
"""conflict_score >= ngưỡng này -> coi là có mâu thuẫn, kích hoạt Debate Module."""

# ---- ValidatorAgent.classify_conflict: quy tắc phân loại mâu thuẫn ----
NO_CONFLICT_CEILING = 0.15
"""conflict_score dưới mức này -> phân loại thẳng là "No Conflict", bỏ qua các rule bên dưới."""

TEMPORAL_CONFLICT_GAP = 0.4
"""Chênh lệch (ptp) recency_weight giữa các agent vượt mức này -> "Temporal Conflict"."""

RELIABILITY_CONFLICT_GAP = 0.5
"""Chênh lệch (ptp) entropy giữa các agent vượt mức này -> "Reliability Conflict"."""

REDUNDANCY_CONFLICT_CEILING = 0.6
"""redundancy_score của bất kỳ agent nào vượt mức này -> "Redundancy Conflict"."""

# ---- DebateAgent ----
DEBATE_ROUNDS = 2
"""Số vòng tranh biện khi conflict_score vượt ngưỡng."""

DEBATE_CONFIDENCE_DECAY_ALPHA = 0.35
"""Tốc độ suy giảm confidence của agent bị phản bác trong mỗi vòng debate."""

# ---- main.py: quyết định tín hiệu cuối cùng từ S_final ----
SIGNAL_NEUTRAL_BAND = 0.05
"""|S_final| dưới mức này -> NEUTRAL; trên mức -> BUY (dương) / SELL (âm)."""

SIGNAL_STRONG_INTENSITY_FLOOR = 0.5
"""|S_final| vượt mức này -> gắn nhãn cường độ "STRONG", dưới mức -> "WEAK"."""
