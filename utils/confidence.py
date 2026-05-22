import numpy as np

def update_confidence(conf_raw: float, rebuttal: float, beta: float = 0.8) -> float:
    """Deterministic confidence update.
    - `rebuttal` ∈ [0, 1] (0 = perfect agreement, 1 = total contradiction).
    - Larger `beta` → stronger decay when faced with strong rebuttals.
    Returns the updated confidence clipped to [0, 1].
    """
    return float(np.clip(conf_raw * np.exp(-beta * rebuttal), 0.0, 1.0))
