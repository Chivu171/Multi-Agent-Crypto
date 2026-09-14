# agents/debate_agent.py (updated)

from utils.llm import ask_llm
import numpy as np
import json
import threading
from typing import List, Dict, Any

from utils.debate_buffer import DebateBuffer
from utils.confidence import update_confidence
from utils.thresholds import DEBATE_CONFIDENCE_DECAY_ALPHA, DEBATE_ROUNDS


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
        "Financial_Agent": "on-chain fundamentals analyst (whale flows, MVRV, supply, miner behavior, ETF holdings)",
        "Market_Agent": "technical market analyst (price action, EMA, RSI, liquidations, funding rate)",
        "Sentiment_Agent": "social sentiment analyst (retail fear/greed, news tone, institutional narrative, macro mood)",
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
                f"conf={a['confidence']:.3f} | {lp_str[:120]}"
            )
        return "\n".join(lines)

    def run_debate(self, agents_output: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Execute multi-turn debate với debate history tích lũy (MADAM-RAG style).
        Mỗi agent giữ đúng domain chuyên môn qua từng round.
        """
        import re
        from utils.display import print_logic_path

        # 1. Đưa toàn bộ output ban đầu vào buffer
        for out in agents_output:
            self.buffer.publish(out["agent_id"], out)

        vectors = self._prepare_vectors(agents_output)
        updated = agents_output
        debate_history = ""  # tích lũy qua các round (MADAM-RAG aggregator)

        for rnd in range(1, self.rounds + 1):
            round_updates = []
            for out in updated:
                agent_id = out["agent_id"]
                rebuttal = self._rebuttal_strength(agent_id, updated, vectors)

                # Confidence decay (alpha=0.35 để tránh decay quá mạnh)
                conf = update_confidence(out["confidence"], rebuttal, beta=self.alpha)

                # Thu thập evidence của các agent khác
                other_evidence = []
                for other in updated:
                    if other["agent_id"] != agent_id:
                        other_evidence.extend(other.get("evidence_chunks", []))

                evidence_text = "\n".join(
                    [e.get("content", "")[:200] for e in other_evidence][:5]
                )
                old_logic_str = json.dumps(out.get("logic_path"), ensure_ascii=False)
                role_desc = self.AGENT_ROLES.get(agent_id, "financial analyst")

                history_section = (
                    f"\nDebate history from previous rounds:\n{debate_history}\n"
                    if debate_history else ""
                )

                prompt = (
                    f"You are {agent_id}, acting strictly as a {role_desc}. "
                    f"This is Round {rnd} of a multi-agent debate.\n\n"
                    f"Your current logic path:\n{old_logic_str}\n"
                    f"{history_section}"
                    f"\nCounter-evidence from other agents (rebuttal strength = {rebuttal:.3f}):\n{evidence_text}\n\n"
                    f"Your confidence after rebuttal: {conf:.3f}.\n\n"
                    f"Update your reasoning based on debate history and new evidence. "
                    f"IMPORTANT: Stay strictly within your domain ({role_desc}). "
                    f"Do NOT adopt arguments outside your expertise. "
                    f"Rewrite logic_path as JSON with exactly 3 key points (max 8 words each, in English). "
                    f'Return only JSON: {{"steps": ["...", "...", "..."]}}, no markdown, no explanation.'
                )

                try:
                    new_logic_raw = ask_llm(prompt, agent_name="debate")
                    json_match = re.search(r'\{.*\}', new_logic_raw, re.DOTALL)
                    new_logic = json.loads(json_match.group()) if json_match else out.get("logic_path")
                except Exception:
                    new_logic = out.get("logic_path")

                new_out = dict(out)
                new_out["confidence"] = conf
                new_out["logic_path"] = new_logic
                # Cập nhật belief_vector strength theo confidence mới
                new_bv = dict(out.get("belief_vector", {}))
                new_bv["strength"] = round(conf, 3)
                new_out["belief_vector"] = new_bv
                self.buffer.publish(agent_id, new_out)
                round_updates.append(new_out)

                print(f"  [{agent_id}] Round {rnd} → confidence: {conf:.3f}")
                print_logic_path(f"sau round {rnd}", new_logic)

            # Cập nhật vectors và tích lũy debate history cho round tiếp
            vectors = {
                o["agent_id"]: np.array([o["belief_vector"]["direction"] * o["belief_vector"]["strength"]])
                for o in round_updates
            }
            updated = round_updates
            debate_history = self._build_debate_history(rnd, round_updates)

        # Trả về snapshot cuối cùng từ buffer
        return [self.buffer.get(out["agent_id"]) for out in updated]
