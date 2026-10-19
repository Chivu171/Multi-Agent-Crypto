"""Direction accuracy at 1, 3 and 7 days (no LLM calls).

A BUY (SELL) call on day D counts as right at horizon h when the open of D+h is
above (below) the open of D. Accuracy alone rewards a BUY-heavy agent in a rising
year, so each accuracy is compared with the chance level of a predictor with the
same BUY share on the same days: p_buy * up_rate + (1 - p_buy) * (1 - up_rate).
edge = accuracy - chance. h-day moves of neighbouring days overlap, so the 95%
interval of the edge comes from a moving-block bootstrap within each window
(block = max(5, h) days), not from a binomial test.

    python scripts/horizon_analysis.py   # -> outputs/horizon_analysis/result.json
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from baselines.cryptotrade.env import DEV_WINDOWS, WINDOWS, load_prices  # noqa: E402

from scripts.asset import RUNS, out_dir  # noqa: E402

OUT = out_dir("outputs/horizon_analysis")
MODEL = "google_gemma-4-26b-a4b-qat"
AGENTS = ("Market_Agent", "Financial_Agent", "Sentiment_Agent")
HORIZONS = (1, 3, 7)
BAND = 0.05  # Mediator neutral band
RESAMPLES, SEED = 5_000, 0
SETS = {"dev": list(DEV_WINDOWS), "test": list(WINDOWS), "pooled": [*DEV_WINDOWS, *WINDOWS]}


def calls(name, prices):
    """strategy -> list of (price index, direction) for the decision days of one window."""
    start, end = {**WINDOWS, **DEV_WINDOWS}[name]
    index = {d["date"]: i for i, d in enumerate(prices)}
    dates = [d["date"] for d in prices if start <= d["date"] <= end][:-1]
    out = {s: [] for s in (*AGENTS, "ours_final", "ct_full")}
    for date in dates:
        day = json.loads((RUNS / name / f"ours__{MODEL}" / "days" / f"{date}.json").read_text())
        if day.get("status") != "ok":
            continue
        for d in day["mediator"]["details"]:
            if d["direction"]:
                out[d["agent_id"]].append((index[date], int(np.sign(d["direction"]))))
        if abs(day["S_final"]) >= BAND:
            out["ours_final"].append((index[date], int(np.sign(day["S_final"]))))
    for step in json.loads((RUNS / name / f"agent_paper_full__{MODEL}" / "steps.json").read_text()):
        if step["action"]:
            out["ct_full"].append((index[step["date"]], int(np.sign(step["action"]))))
    return out


def outcomes(pairs, opens, h):
    """(direction, went_up) for calls whose D+h open exists."""
    rows = [(d, opens[i + h] > opens[i]) for i, d in pairs if i + h < len(opens)]
    return np.array([r[0] for r in rows]), np.array([r[1] for r in rows])


def edge(dirs, ups):
    acc = np.mean((dirs > 0) == ups)
    p_buy, up = np.mean(dirs > 0), np.mean(ups)
    return acc, p_buy * up + (1 - p_buy) * (1 - up)


def block_sample(n, block, rng):
    starts = rng.integers(0, n, size=int(np.ceil(n / block)))
    return (starts[:, None] + np.arange(block)[None, :]).ravel()[:n] % n


def analyse(per_window, h):
    dirs = np.concatenate([d for d, _ in per_window])
    ups = np.concatenate([u for _, u in per_window])
    acc, chance = edge(dirs, ups)
    rng, stats = np.random.default_rng(SEED), np.empty(RESAMPLES)
    for k in range(RESAMPLES):
        parts = [(d[idx], u[idx]) for d, u in per_window if len(d)
                 for idx in [block_sample(len(d), max(5, h), rng)]]
        a, c = edge(np.concatenate([p[0] for p in parts]), np.concatenate([p[1] for p in parts]))
        stats[k] = a - c
    return {"n": int(len(dirs)), "accuracy": float(acc), "chance": float(chance), "edge": float(acc - chance),
            "edge_ci95": [float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))],
            "buy_share": float(np.mean(dirs > 0)), "up_rate": float(np.mean(ups))}


def main():
    prices = load_prices()
    opens = np.array([d["open"] for d in prices])
    window_calls = {w: calls(w, prices) for w in SETS["pooled"]}
    result = {}
    for s, windows in SETS.items():
        for strategy in (*AGENTS, "ours_final", "ct_full"):
            for h in HORIZONS:
                per_window = [outcomes(window_calls[w][strategy], opens, h) for w in windows]
                result.setdefault(s, {}).setdefault(strategy, {})[h] = analyse(per_window, h)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "result.json").write_text(json.dumps({"resamples": RESAMPLES, "seed": SEED, "result": result}, indent=2))
    for s, res in result.items():
        print(f"\n{s.upper()}  accuracy / chance with same BUY share -> edge [95% CI]  (n, BUY share)")
        for strategy, by_h in res.items():
            cells = [f"{h}d {r['accuracy'] * 100:4.1f}/{r['chance'] * 100:4.1f} -> {r['edge'] * 100:+5.1f} "
                     f"[{r['edge_ci95'][0] * 100:+5.1f},{r['edge_ci95'][1] * 100:+5.1f}]" for h, r in by_h.items()]
            print(f"  {strategy:16s} " + "  ".join(cells) + f"  (n={by_h[1]['n']}, BUY {by_h[1]['buy_share'] * 100:.0f}%)")


if __name__ == "__main__":
    main()
