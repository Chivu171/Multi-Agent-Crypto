import datetime

import numpy as np

# ==============================
# Penalty utility functions
# ==============================

def entropy_penalty(entropy: float, max_entropy: float = 1.0) -> float:
    """Return a penalty factor (0..1) that reduces weight for noisy text.
    Higher entropy → larger penalty (closer to 1)."""
    # Normalize entropy to [0,1] and treat it as a direct penalty.
    normalized = min(max(entropy / max_entropy, 0.0), 1.0)
    return normalized


def redundancy_penalty(redundancy_score: float, max_score: float = 1.0) -> float:
    """Penalty for duplicated / copy‑paste evidence.
    Larger redundancy → larger penalty (closer to 1)."""
    normalized = min(max(redundancy_score / max_score, 0.0), 1.0)
    return normalized


def time_decay_penalty(delta_t_seconds: float, gamma: float = 1e-5) -> float:
    """Exponential decay factor based on age of the information.
    Older data → smaller factor (approaches 0)."""
    # e^{-γ·Δt} ensures the factor is in (0,1].
    return np.exp(-gamma * delta_t_seconds)

def recency_weight_from_iso_timestamp(fetched_at: str, gamma: float = 1e-5) -> float:
    """Recency weight (0..1] from an ISO 8601 timestamp of when data was fetched.
    Just-fetched data → close to 1.0; the longer it's been since the fetch
    (e.g. a stale cache after an API outage), the closer this approaches 0."""
    fetched = datetime.datetime.fromisoformat(fetched_at)
    delta_seconds = max((datetime.datetime.now(datetime.timezone.utc) - fetched).total_seconds(), 0.0)
    return float(time_decay_penalty(delta_seconds, gamma))


# Helper to combine all penalties into a single weight factor
def combined_weight(base_weight: float, entropy: float, redundancy: float, delta_t: float, gamma: float = 1e-5) -> float:
    """Calculate final weight ω = base_weight × (1‑entropy_penalty) × (1‑redundancy_penalty) × time_decay"""
    ent_pen = entropy_penalty(entropy)
    red_pen = redundancy_penalty(redundancy)
    time_factor = time_decay_penalty(delta_t, gamma)
    # Subtract penalties from 1 so that higher penalty reduces weight.
    return base_weight * (1 - ent_pen) * (1 - red_pen) * time_factor
