# agents/debate_agent.py (updated)

from utils.llm import ask_llm
import numpy as np
import json
from copy import deepcopy
from typing import List, Dict, Any

from utils.debate_buffer import DebateBuffer
from utils.confidence import update_confidence
from utils.thresholds import DEBATE_CONFIDENCE_DECAY_ALPHA, DEBATE_ROUNDS
from utils.grounding import build_evidence_registry, request_grounded_claims, render_claims, GroundingError


def _cosine_distance(v1: np.ndarray, v2: np.ndarray) -> float:
    """Return 1 - cosine similarity (0 = identical, up to 2 for opposite)."""
    norm1, norm2 = np.linalg.norm(v1), np.linalg.norm(v2)
    if norm1 == 0 or norm2 == 0:
        return 1.0
    cosine = np.dot(v1, v2) / (norm1 * norm2)
    return 1.0 - float(cosine)


def _jaccard_distance(evs_a: List[Dict[str, Any]], evs_b: List[Dict[str, Any]]) -> float:
    """Jaccard distance between two sets of evidence chunks (tokenised by whitespace)."""
    def tokens(chunk: Dict[str, Any]) -> set:
        txt = chunk.get("content", "").lower()
        return set(txt.split())
    set_a = set().union(*(tokens(c) for c in evs_a))
    set_b = set().union(*(tokens(c) for c in evs_b))
    if not set_a and not set_b:
        return 0.0
    inter = len(set_a & set_b)
    union = len(set_a | set_b)
    return 1.0 - inter / union


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Simple Levenshtein edit distance (character based)."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1, 1):
        current_row = [i]
        for j, c2 in enumerate(s2, 1):
            insertions = previous_row[j] + 1
            deletions = current_row[j - 1] + 1
            substitutions = previous_row[j - 1] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


def _logic_path_distance(p1: Any, p2: Any) -> float:
    """Distance between two JSON‑serialisable logic_path objects.
    Normalised by dividing by max possible length (len of longer string)."""
    s1 = json.dumps(p1, sort_keys=True)
    s2 = json.dumps(p2, sort_keys=True)
    dist = _levenshtein_distance(s1, s2)
    max_len = max(len(s1), len(s2))
    return dist / max_len if max_len else 0.0


class DebateAgent:
    """Deterministic multi‑turn debate handling.

    Parameters
    ----------
    rounds: int
        Number of debate iterations.
    alpha: float
        Scaling factor used in the confidence update function (passed to utils.update_confidence).
    weights: tuple of three floats
        Weighting for belief divergence, evidence contradiction, and logic‑path distance.
    """

    def __init__(self, rounds: int = DEBATE_ROUNDS, alpha: float = DEBATE_CONFIDENCE_DECAY_ALPHA, weights: tuple = (1/3, 1/3, 1/3)):
        self.rounds = rounds
        self.alpha = alpha
        self.w_belief, self.w_evidence, self.w_logic = weights
        self.buffer = DebateBuffer()

    def _prepare_vectors(self, agents_output: List[Dict[str, Any]]) -> Dict[str, np.ndarray]:
        return {
            out["agent_id"]: np.array([out["belief_vector"]["direction"] * out["belief_vector"]["strength"]])
            for out in agents_output
        }

    def _rebuttal_strength(self, target_id: str, agents_output: List[Dict[str, Any]], vectors: Dict[str, np.ndarray]) -> float:
        target = next(o for o in agents_output if o["agent_id"] == target_id)
        strengths = []
        for other in agents_output:
            if other["agent_id"] == target_id:
                continue
            belief = _cosine_distance(vectors[target_id], vectors[other["agent_id"]])
            evidence = _jaccard_distance(target.get("evidence_chunks", []), other.get("evidence_chunks", []))
            logic = _logic_path_distance(target.get("logic_path"), other.get("logic_path"))
            strength = (
                self.w_belief * belief +
                self.w_evidence * evidence +
                self.w_logic * logic
            )
            strengths.append(strength)
        raw = float(np.mean(strengths)) if strengths else 0.5
        # Normalize về [0, 1] — cosine dist có thể lên tới 2.0
        return float(np.clip(raw / 1.5, 0.0, 1.0))

    # Vai trò chuyên môn của từng agent — dùng để giữ domain trong debate
    AGENT_ROLES = {
        "Financial_Agent": "chuyên gia on-chain, chỉ phân tích các quan sát và nguồn thực sự được cung cấp",
        "Market_Agent": "chuyên gia phân tích kỹ thuật thị trường (hành động giá, EMA, RSI, thanh lý, funding rate)",
        "Sentiment_Agent": "chuyên gia phân tích tâm lý xã hội (fear/greed retail, sắc thái tin tức, tường thuật tổ chức, tâm lý vĩ mô)",
    }

    @staticmethod
    def _build_debate_history(round_num: int, agents_state: List[Dict[str, Any]]) -> str:
        """Tóm tắt trạng thái debate sau round_num — MADAM-RAG aggregator style."""
        lines = [f"[Debate History — after Round {round_num}]"]
        for a in agents_state:
            lp = a.get("logic_path", "")
            if isinstance(lp, dict):
                steps = lp.get("steps", [])
                lp_str = " → ".join(steps) if steps else json.dumps(lp, ensure_ascii=False)
            elif isinstance(lp, list):
                lp_str = " → ".join(str(s) for s in lp)
            else:
                lp_str = str(lp)
            lines.append(
                f"  {a['agent_id']}: signal={a.get('signal', '?')}, "
                f"conf={a['confidence']:.3f} | {lp_str}"
            )
        return "\n".join(lines)

    def run_debate(self, agents_output: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Execute multi-turn debate với debate history tích lũy (MADAM-RAG style).
        Mỗi agent giữ đúng domain chuyên môn qua từng round.
        """
        from utils.display import print_logic_path

        # Original sources stay separate from opinions generated during debate.
        self.evidence_registry = build_evidence_registry(agents_output)
        self.buffer = DebateBuffer()
        # 1. Đưa toàn bộ output ban đầu vào buffer
        for out in agents_output:
            self.buffer.publish(out["agent_id"], out)

        vectors = self._prepare_vectors(agents_output)
        updated = deepcopy(agents_output)
        debate_history = ""  # tích lũy qua các round (MADAM-RAG aggregator)

        for rnd in range(1, self.rounds + 1):
            round_updates = []
            for out in updated:
                agent_id = out["agent_id"]
                rebuttal = self._rebuttal_strength(agent_id, updated, vectors)

                # Confidence decay (alpha=0.35 để tránh decay quá mạnh)
                conf = update_confidence(out["confidence"], rebuttal, beta=self.alpha)

                old_logic_str = json.dumps(out.get("logic_path"), ensure_ascii=False)
                role_desc = self.AGENT_ROLES.get(agent_id, "chuyên gia phân tích tài chính")

                history_section = (
                    f"\nDebate history from previous rounds:\n{debate_history}\n"
                    if debate_history else ""
                )

                prompt = (
                    f"Bạn là {agent_id}, đóng vai nghiêm ngặt là {role_desc}. "
                    f"Đây là Vòng {rnd} của một cuộc tranh luận đa đại lý (multi-agent debate).\n\n"
                    f"Lộ trình suy luận hiện tại của bạn:\n{old_logic_str}\n"
                    f"{history_section}"
                    f"\nTín hiệu hiện tại: {out.get('signal')}. Cường độ phản biện: {rebuttal:.3f}.\n"
                    f"Confidence đề xuất sau phản biện: {conf:.3f}; chỉ áp dụng nếu nhận định đạt kiểm tra nguồn.\n"
                    f"Cập nhật lập luận của bạn dựa trên lịch sử tranh luận và bằng chứng mới. "
                    f"QUAN TRỌNG: Bám sát nghiêm ngặt trong phạm vi chuyên môn của bạn ({role_desc}). "
                    f"Danh sách evidence chứa đầy đủ nguồn của bạn VÀ các agent khác; phân biệt qua agent_id. "
                    f"Lập luận cũ/lịch sử là ý kiến, không phải bằng chứng đã xác minh. "
                    f"Chỉ nêu dữ kiện có nguồn; tin tức được cung cấp được phép dùng dù ngoài danh mục chỉ số. "
                    f"Phân biệt dữ kiện, suy luận và giả thuyết. Nêu cả cơ sở và giới hạn của tín hiệu hiện tại. "
                    f"Trả 1-3 claims theo schema, mỗi claim có citations với evidence_id và trích đoạn nguyên văn."
                )

                new_out = deepcopy(out)
                try:
                    claims, audit = request_grounded_claims(
                        prompt, self.evidence_registry, agent_name="debate", ask=ask_llm,
                    )
                    new_out["confidence"] = conf
                    new_out["logic_path"] = {"steps": render_claims(claims)}
                    new_out["grounded_claims"] = claims
                    new_out["belief_vector"]["strength"] = round(conf, 3)
                except GroundingError as exc:
                    audit = exc.audit
                    # Reject the whole update, including confidence and strength.
                    # An invalid explanation must not affect later rounds' state.
                    print(f"  [{agent_id}] Round {rnd}: nguồn chưa đạt kiểm tra; giữ trạng thái trước vòng.")
                new_out.setdefault("debate_audit", []).append({"round": rnd, **audit})
                new_out["grounding_evidence"] = self.evidence_registry
                self.buffer.publish(agent_id, new_out)
                round_updates.append(new_out)

                print(f"  [{agent_id}] Round {rnd} → confidence: {new_out['confidence']:.3f} ({audit['status']})")
                print_logic_path(f"sau round {rnd}", new_out.get("logic_path"))

            # Cập nhật vectors và tích lũy debate history cho round tiếp
            vectors = {
                o["agent_id"]: np.array([o["belief_vector"]["direction"] * o["belief_vector"]["strength"]])
                for o in round_updates
            }
            updated = round_updates
            debate_history = self._build_debate_history(rnd, round_updates)

        # Trả về snapshot cuối cùng từ buffer
        return [self.buffer.get(out["agent_id"]) for out in updated]
