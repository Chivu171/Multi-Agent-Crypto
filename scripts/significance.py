"""Statistical tests for the main comparisons (no LLM calls).

1. Paired moving-block bootstrap of the mean total-return difference between two
   strategies over a set of windows. Days are resampled in blocks of BLOCK days with
   the same indices for both strategies, each strategy's daily returns are compounded
   per window, and the statistic is the mean over windows of the return difference.
2. Exact two-sided binomial test of direction accuracy against 50%, with a Wilson
   95% interval, for each agent and for the final decisions.

    python scripts/significance.py   # -> outputs/significance/result.json
"""
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scripts.trend_variants as tv  # noqa: E402
from baselines.cryptotrade.env import DEV_WINDOWS, WINDOWS, load_prices  # noqa: E402
from scripts.agent_regime_analysis import day_records  # noqa: E402

RUNS = Path("outputs/baselines/cryptotrade")
OUT = Path("outputs/significance")
MODEL = "google_gemma-4-26b-a4b-qat"
CT_FULL = f"agent_paper_full__{MODEL}"
BLOCK, RESAMPLES, SEED = 5, 10_000, 0
SETS = {"dev": list(DEV_WINDOWS), "test": list(WINDOWS), "pooled": [*DEV_WINDOWS, *WINDOWS]}


def ct_returns(name):
    steps = json.loads((RUNS / name / CT_FULL / "steps.json").read_text())
    return np.array([s["today_roi"] for s in steps])


def ours_returns(name, prices, run="ours", **variant):
    tv.RUN_NAME = f"{run}__{MODEL}"
    window = tv.load_window(name, prices)
    actions = tv.actions_for(window, **variant) if variant else [r["saved_action"] for r in window["rows"]]
    return np.array(tv.simulate(window, actions, daily=True)["daily_returns"])


def block_indices(n, rng):
    starts = rng.integers(0, n, size=math.ceil(n / BLOCK))
    return (starts[:, None] + np.arange(BLOCK)[None, :]).ravel()[:n] % n  # circular blocks


def paired_bootstrap(pairs):
    """pairs: list of (returns_a, returns_b) per window -> observed diff, 95% CI, two-sided p."""
    assert all(len(a) == len(b) for a, b in pairs), "daily series must cover the same days"
    observed = np.mean([np.prod(1 + a) - np.prod(1 + b) for a, b in pairs])
    rng = np.random.default_rng(SEED)
    stats = np.empty(RESAMPLES)
    for k in range(RESAMPLES):
        diffs = []
        for a, b in pairs:
            idx = block_indices(len(a), rng)
            diffs.append(np.prod(1 + a[idx]) - np.prod(1 + b[idx]))
        stats[k] = np.mean(diffs)
    p = min(1.0, 2 * min((stats <= 0).mean(), (stats >= 0).mean()))
    return {"diff": float(observed), "ci95": [float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))],
            "p": float(p)}


def binomial_p(k, n):
    """Exact two-sided test of k successes in n against p=0.5."""
    probs = [math.comb(n, i) / 2 ** n for i in range(n + 1)]
    return min(1.0, sum(q for q in probs if q <= probs[k] * (1 + 1e-9)))


def wilson(k, n, z=1.96):
    phat, denom = k / n, 1 + z * z / n
    centre, half = (phat + z * z / (2 * n)) / denom, z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / denom
    return [centre - half, centre + half]


def accuracy_test(k, n):
    return {"accuracy": k / n, "n": n, "ci95": wilson(k, n), "p": binomial_p(k, n)}


def return_tests(prices):
    filter_trend = json.loads((tv.OUT / "selected.json").read_text())["filter"]["trend"]
    comparisons = {
        "ours_vs_ct_full": lambda w: (ours_returns(w, prices), ct_returns(w)),
        "ours_filter_vs_ct_full": lambda w: (ours_returns(w, prices, trend=filter_trend, use_filter=True), ct_returns(w)),
    }
    out = {name: {s: paired_bootstrap([f(w) for w in windows]) for s, windows in SETS.items()}
           for name, f in comparisons.items()}
    for run in ("ours_trend", "ours_debias", "ours_flip"):  # LLM reruns, dev only, against eval-v1
        out[f"{run}_vs_ours"] = {"dev": paired_bootstrap([(ours_returns(w, prices, run), ours_returns(w, prices))
                                                          for w in DEV_WINDOWS])}
    return out


def accuracy_tests(prices):
    tv.RUN_NAME = f"ours__{MODEL}"
    out = {}
    for s, windows in SETS.items():
        import scripts.agent_regime_analysis as ara
        ara.RUN_NAME = tv.RUN_NAME
        records = [r for w in windows for r in day_records(w, prices)]
        res = {}
        for agent in tv.AGENTS:
            hits = [(r["dir"].get(agent, 0) > 0) == r["up_next"] for r in records if r["dir"].get(agent, 0)]
            res[agent] = accuracy_test(sum(hits), len(hits))
        hits = [(r["S_final"] > 0) == r["up_next"] for r in records if abs(r["S_final"]) >= 0.05]
        res["ours_final"] = accuracy_test(sum(hits), len(hits))
        k = n = 0
        for w in windows:
            r = json.loads((RUNS / w / CT_FULL / "result.json").read_text())
            n += r["directional_days"]
            k += round(r["direction_accuracy"] * r["directional_days"])
        res["ct_full_final"] = accuracy_test(k, n)
        out[s] = res
    return out


def main():
    prices = load_prices()
    result = {"block": BLOCK, "resamples": RESAMPLES, "seed": SEED,
              "returns": return_tests(prices), "accuracy": accuracy_tests(prices)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "result.json").write_text(json.dumps(result, indent=2))
    print("Mean total-return difference (percentage points), paired block bootstrap")
    for name, sets in result["returns"].items():
        for s, r in sets.items():
            print(f"  {name:24s} {s:7s} {r['diff'] * 100:+7.2f}  CI [{r['ci95'][0] * 100:+7.2f}, {r['ci95'][1] * 100:+7.2f}]"
                  f"  p={r['p']:.3f}")
    print("Direction accuracy vs 50% (exact binomial, Wilson 95% CI)")
    for s, res in result["accuracy"].items():
        for name, r in res.items():
            print(f"  {s:7s} {name:16s} {r['accuracy'] * 100:5.1f}% (n={r['n']:3d})  "
                  f"CI [{r['ci95'][0] * 100:4.1f}, {r['ci95'][1] * 100:4.1f}]  p={r['p']:.3f}")


if __name__ == "__main__":
    main()
