# agents/debate_agent.py (updated)

from utils.llm import ask_llm
import numpy as np
import json
import threading
from typing import List, Dict, Any

from utils.debate_buffer import DebateBuffer
from utils.confidence import update_confidence


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

    def __init__(self, rounds: int = 3, alpha: float = 0.5, weights: tuple = (1/3, 1/3, 1/3)):
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
        return float(np.mean(strengths)) if strengths else 0.5

    def run_debate(self, agents_output: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Execute deterministic debate và cập nhật logic_path bằng LLM.
        Sau mỗi vòng (round) sẽ in ra trạng thái hiện tại của mỗi agent.
        """
        # 1. Đưa toàn bộ output ban đầu vào buffer
        for out in agents_output:
            self.buffer.publish(out["agent_id"], out)

        vectors = self._prepare_vectors(agents_output)
        updated = agents_output

        for rnd in range(1, self.rounds + 1):
            round_updates = []
            for out in updated:
                agent_id = out["agent_id"]
                rebuttal = self._rebuttal_strength(agent_id, updated, vectors)
                # Cập nhật confidence
                conf = out["confidence"]
                conf = update_confidence(conf, rebuttal, beta=self.alpha)

                # Thu thập evidence của các agent khác
                other_evidence = []
                for other in updated:
                    if other["agent_id"] != agent_id:
                        other_evidence.extend(other.get("evidence_chunks", []))

                # Prompt cho LLM (tiếng Việt)
                prompt = (
                    "Bạn là một engine lý luận trong một cuộc tranh luận đa‑agent. "
                    f"Dựa trên độ thay đổi confidence (strength = {rebuttal:.3f}) và các đoạn bằng chứng từ các agent khác, "
                    "Bạn là một công cụ suy luận cho phiên tranh luận đa‑agent. "
                    "Dựa trên mức độ thay đổi confidence (rebuttal strength = {rebuttal:.3f}) "
                    "và các đoạn bằng chứng từ các agent khác, hãy tạo một JSON‑serialisable "
                    "`logic_path` mô tả các bước lý luận cập nhật. "
                    "Chỉ trả về JSON mà không có bất kỳ văn bản nào khác."
                    "\nCác đoạn bằng chứng:\n"
                    + "\n".join([e.get("content", "")[:200] for e in other_evidence][:5])
                    + f"\nConfidence hiện tại: {conf:.3f}"
                )
                try:
                    new_logic_raw = ask_llm(prompt, agent_name="debate")
                    try:
                        new_logic = json.loads(new_logic_raw)
                    except Exception:
                        new_logic = out.get("logic_path")
                except Exception:
                    new_logic = out.get("logic_path")

                new_out = dict(out)
                new_out["confidence"] = conf
                new_out["logic_path"] = new_logic
                self.buffer.publish(agent_id, new_out)
                round_updates.append(new_out)

                # In ra thông tin cho người dùng
                print(f"[Vòng {rnd}] Agent: {agent_id}\n  Confidence: {conf:.3f}\n  Logic Path: {json.dumps(new_logic, ensure_ascii=False, indent=2)}\n")

            # Cập nhật vectors cho vòng tiếp theo
            vectors = {o["agent_id"]: np.array([o["belief_vector"]["direction"] * o["belief_vector"]["strength"]]) for o in round_updates}
            updated = round_updates

        # Trả về danh sách cuối cùng (sau tất cả các vòng)
        final_outputs = []
        for out in updated:
            final_outputs.append(self.buffer.get(out["agent_id"]))
        return final_outputs
