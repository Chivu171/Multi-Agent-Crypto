# agents/validator_agent.py

import json
import numpy as np
from typing import List, Dict, Any, Tuple
from utils.llm import ask_llm  # Tận dụng LLM layer đã hoàn thành ở Thứ 3
from utils.prompts import VALIDATOR_AGENT_PROMPT
from utils.thresholds import (
    DEBATE_CONFIDENCE_DECAY_ALPHA,
    DEBATE_ROUNDS,
    DEFAULT_CONFLICT_ALPHA,
    DEFAULT_CONFLICT_THRESHOLD,
    NO_CONFLICT_CEILING,
    RELIABILITY_CONFLICT_GAP,
    REDUNDANCY_CONFLICT_CEILING,
    TEMPORAL_CONFLICT_GAP,
)

# Import DebateAgent for conditional debate integration
from agents.debate_agent import DebateAgent
from utils.grounding import build_evidence_registry, request_grounded_claims, render_claims, GroundingError

class ValidatorAgent:
    def __init__(self, alpha: float = DEFAULT_CONFLICT_ALPHA, threshold: float = DEFAULT_CONFLICT_THRESHOLD, use_llm: bool = True):
        """
        Alpha: Trọng số cân bằng giữa KL Divergence (Học thuật) và Variance (Thực nghiệm)
        Threshold: Ngưỡng biên kích hoạt vòng tranh luận (Conditional Debate Trigger)
        use_llm: Cờ cho phép gọi mô hình ngôn ngữ lớn để chạy Root Cause Analysis
        """
        self.alpha = alpha
        self.threshold = threshold
        self.use_llm = use_llm
        self.rca_grounding = {"status": "not_run"}

    def _kl_divergence(self, p: np.ndarray, q: np.ndarray) -> float:
        """Tính toán Kullback-Leibler Divergence giữa 2 phân phối niềm tin có làm mượt (Smoothing)"""
        epsilon = 1e-9
        p = np.clip(p, epsilon, 1.0)
        q = np.clip(q, epsilon, 1.0)
        p /= np.sum(p)
        q /= np.sum(q)
        return float(np.sum(p * np.log(p / q)))

    def calculate_conflict_core(self, agents_output: List[Dict[str, Any]]) -> Tuple[float, float, float]:
        """
        [Task 1] Toán tử định lượng lai (Hybrid Formulation Matrix)
        """
        belief_distributions = []
        raw_vectors = []
        
        for out in agents_output:
            bv = out["belief_vector"]
            direction = bv["direction"] # -1 (Bearish), 1 (Bullish), 0 (Neutral)
            strength = bv["strength"]
            
            # Ánh xạ tuyến tính liên tục (Linear Interpolation Projection)
            # Tránh nghịch đảo niềm tin khi độ tự tin thấp
            x = direction * strength
            p_bullish = 0.5 + 0.5 * x
            p_bearish = 0.5 - 0.5 * x
            dist = [p_bearish, p_bullish]
                
            belief_distributions.append(np.array(dist))
            raw_vectors.append(x) # scalar representation phục vụ tính Variance

        # 1. Tính Mean Pairwise KL Divergence
        kl_scores = []
        n = len(belief_distributions)
        for i in range(n):
            for j in range(n):
                if i != j:
                    kl_scores.append(self._kl_divergence(belief_distributions[i], belief_distributions[j]))
        mean_kl = float(np.mean(kl_scores)) if kl_scores else 0.0 # -> 0 : tương đồg, -> vô hạn: không tương đồng

        # 2. Tính Variance của các quyết định thực tế
        variance_score = float(np.var(raw_vectors)) # -> 0 : tương đồng, -> 1 : không tương đồng

        # 3. Hybrid Conflict Score
        conflict_score = float(self.alpha * mean_kl + (1 - self.alpha) * variance_score)
        return conflict_score, mean_kl, variance_score

    def classify_conflict(self, agents_output: List[Dict[str, Any]], conflict_score: float) -> List[str]:
        """
        [Task 2.1] Deterministic Conflict Classifier
        Phân loại mâu thuẫn hệ thống dựa trên các quy tắc biên cấu trúc
        """
        if conflict_score < NO_CONFLICT_CEILING:
            return ["No Conflict"]

        categories = []
        signals = [out["signal"] for out in agents_output]
        recency_weights = [out["metadata"]["recency_weight"] for out in agents_output]
        redundancy_scores = [out["metadata"]["redundancy_score"] for out in agents_output]
        entropies = [out["metadata"]["entropy"] for out in agents_output]

        # Rule 1: Signal Conflict (Xung đột xu hướng trực tiếp)
        if "BUY" in signals and "SELL" in signals:
            categories.append("Signal Conflict")

        # Rule 2: Temporal Conflict (Xung đột thời gian/Độ trễ dữ liệu)
        if np.ptp(recency_weights) > TEMPORAL_CONFLICT_GAP:
            categories.append("Temporal Conflict")

        # Rule 3: Reliability Conflict (Xung đột chất lượng nguồn/Entropy)
        if np.ptp(entropies) > RELIABILITY_CONFLICT_GAP:
            categories.append("Reliability Conflict")

        # Rule 4: Redundancy Conflict (Mâu thuẫn do khuếch đại/Thao túng thông tin)
        if any(r > REDUNDANCY_CONFLICT_CEILING for r in redundancy_scores):
            categories.append("Redundancy Conflict")

        return categories if categories else ["Unclassified Structural Anomaly"]

    def run_root_cause_analysis(self, agents_output: List[Dict[str, Any]], categories: List[str]) -> str:
        """
        [Task 2.2] Root Cause Analysis (RCA) Layer
        Trích xuất dữ liệu thô và nhờ LLM tổng hợp lý do bản chất bằng văn bản học thuật
        """
        # Trích xuất signals nội bộ để tránh lỗi NameError trong Fallback
        signals_map = {out["agent_id"]: out["signal"] for out in agents_output}
        
        # Đóng gói ngữ cảnh tối giản để tiết kiệm token
        rca_context = []
        for out in agents_output:
            rca_context.append({
                "agent_id": out["agent_id"],
                "signal": out["signal"],
                "confidence": out["confidence"],
                "logic_path": out["logic_path"],
                "note": "Agent opinion; verify against original evidence, not an independent source",
            })

        prompt = VALIDATOR_AGENT_PROMPT.format(
            categories=', '.join(categories),
            rca_context=json.dumps(rca_context, indent=2, ensure_ascii=False)
        )
        
        # Nếu chưa cấu hình sử dụng LLM hoặc gọi lỗi, trả về phân tích thô deterministic
        if not self.use_llm:
            self.rca_grounding = {"status": "disabled"}
            return f"RCA Triggered for {categories}. Core discrepancy found in agent signals: {signals_map}"

        registry = build_evidence_registry(agents_output)
        try:
            claims, audit = request_grounded_claims(prompt, registry, agent_name="validator", ask=ask_llm)
            self.rca_grounding = {**audit, "claims": claims, "evidence": registry}
            return "\n".join(render_claims(claims))
        except GroundingError as exc:
            self.rca_grounding = {**exc.audit, "evidence": registry}
            return f"[RCA chưa có giải thích đạt kiểm tra nguồn] Tín hiệu đã quan sát: {signals_map}"

    def evaluate_pipeline(
        self,
        agents_output: List[Dict[str, Any]],
        missing_agents: List[str] | None = None,
    ) -> Dict[str, Any]:
        """
        Execution Pipeline chính của Validator Agent

        missing_agents: tên các specialist agent đã lỗi/không trả được kết quả
        (đã bị loại khỏi agents_output trước khi vào đây). Dùng để phân biệt
        "đồng thuận thật" với "chỉ còn 1 agent nên không có gì để so sánh".
        """
        missing_agents = missing_agents or []
        self.rca_grounding = {"status": "not_run"}
        n = len(agents_output)

        # Với n < 2 không có phép so sánh nào là hợp lệ (KL/variance cần tối
        # thiểu 2 điểm dữ liệu) — trả trạng thái "không đủ dữ liệu" tường minh
        # thay vì để công thức âm thầm trả 0.0 và bị hiểu nhầm là "No Conflict".
        if n < 2:
            return {
                "conflict_score": None,
                "metrics": {"mean_pairwise_kl": None, "decision_variance": None},
                "conflict_detected": False,
                "conflict_categories": ["Insufficient Data — cannot assess conflict"],
                "root_cause_analysis": (
                    f"N/A - Insufficient agent outputs (n={n}) to perform conflict "
                    f"analysis. Missing agents: {missing_agents or ['unknown']}."
                ),
                "trigger_debate_module": False,
                "debate_updated_outputs": None,
                "degraded_mode": True,
                "missing_agents": missing_agents,
                "rca_grounding": self.rca_grounding,
                "debate_status": "not_run",
                "explanations_valid": False,
            }

        # 1. Định lượng mâu thuẫn
        conflict_score, mean_kl, variance = self.calculate_conflict_core(agents_output)
        
        # 2. Phát hiện biến số biên
        conflict_detected = conflict_score >= self.threshold
        
        # 3. Phân loại cấu trúc và RCA
        conflict_categories = self.classify_conflict(agents_output, conflict_score)
        
        rca_report = "N/A - System in state of consensus."
        if conflict_detected:
            rca_report = self.run_root_cause_analysis(agents_output, conflict_categories)
        
        # 4. Conditional Debate Trigger – run debate if conflict detected
        debate_updated_outputs = None
        debate_status = "not_run"
        post_conflict = None
        if conflict_detected:
            print("\n[Step 3] Khởi chạy Debate Module...")

            # Instantiate DebateAgent — alpha thấp để tránh confidence decay quá mạnh
            debate_agent = DebateAgent(rounds=DEBATE_ROUNDS, alpha=DEBATE_CONFIDENCE_DECAY_ALPHA)
            debate_updated_outputs = debate_agent.run_debate(agents_output)
            statuses = [item["status"] for out in debate_updated_outputs for item in out.get("debate_audit", [])]
            debate_status = ("accepted" if statuses and all(s == "accepted" for s in statuses)
                             else "partial" if "accepted" in statuses else "rejected")
            post_conflict = self.calculate_conflict_core(debate_updated_outputs)[0]
        
        # 5. Assemble final result
        return {
            "conflict_score": round(conflict_score, 4),
            "metrics": {
                "mean_pairwise_kl": round(mean_kl, 4),
                "decision_variance": round(variance, 4)
            },
            "conflict_detected": conflict_detected,
            "conflict_categories": conflict_categories,
            "root_cause_analysis": rca_report,
            "trigger_debate_module": conflict_detected,
            "debate_updated_outputs": debate_updated_outputs,
            "degraded_mode": n < 3,
            "missing_agents": missing_agents,
            "rca_grounding": self.rca_grounding,
            "debate_status": debate_status,
            "conflict_score_after_debate": round(post_conflict, 4) if post_conflict is not None else None,
            "explanations_valid": self.rca_grounding["status"] != "rejected" and debate_status not in {"partial", "rejected"},
        }
