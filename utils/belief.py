# utils/belief.py

from utils.schema import SIGNAL_MAP


def build_belief_vector(signal: str, confidence: float):
    return {
        "direction": SIGNAL_MAP[signal],
        "strength": round(confidence, 3)
    }