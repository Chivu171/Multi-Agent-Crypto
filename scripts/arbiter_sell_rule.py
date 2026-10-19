"""Exploratory: long-run reliability arbiter on conflict days + asymmetric SELL rule.

Both parts were designed after the test periods had been seen (reliability_arbiter.py,
sell_rule.py), so the test numbers here are exploratory, not a clean held-out result.

- Conflict days (>= 1 BUY and >= 1 SELL among the specialists): the direction comes from
  the agents' record on all PAST conflict days, carried across the six windows in time
  order (Beta(5, 5) prior). A contested SELL is never executed (it cannot meet a
  "stronger evidence" bar), so the arbiter can only BUY or stay out.
- Other days: BUY at S_final >= +0.05; SELL only at S_final <= -k (k = None: never SELL).
k is chosen on dev; the chosen k is evaluated once on test.

    python scripts/arbiter_sell_rule.py   # -> outputs/arbiter_sell_rule/result.json
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scripts.significance as sig  # noqa: E402
from baselines.cryptotrade.env import DEV_WINDOWS, WINDOWS, load_prices  # noqa: E402
from scripts.trend_variants import AGENTS, load_window, simulate  # noqa: E402

from scripts.asset import out_dir  # noqa: E402

OUT = out_dir("outputs/arbiter_sell_rule")
PRIOR, BAND = 5, 0.05
KS = (0.05, 0.10, 0.15, 0.20, 0.30, None)


def actions_all(windows, k):
    """Actions for every window, walking the windows in time order to carry the records."""
    right, seen, out = {a: 0 for a in AGENTS}, {a: 0 for a in AGENTS}, {}
    for w in sorted(windows, key=lambda w: w["rows"][0]["date"]):
        opens, rows, acts = w["opens"], w["rows"], []
        for i, row in enumerate(rows):
            dirs = {a: int(np.sign(c)) for a, c in row["contrib"].items()}
            if not row["ok"]:
                acts.append(0.0)
                continue
            if 1 in dirs.values() and -1 in dirs.values():
                rel = {a: (right[a] + PRIOR) / (seen[a] + 2 * PRIOR) for a in AGENTS}
                acts.append(0.5 if sum(dirs[a] * (rel[a] - 0.5) for a in AGENTS) > 0 else 0.0)
                nxt = opens[rows[i + 1]["i"]] if i + 1 < len(rows) else w["last_open"]
                for a in AGENTS:
                    if dirs[a]:
                        seen[a] += 1
                        right[a] += (dirs[a] > 0) == (nxt > opens[row["i"]])
                continue
            s = sum(row["contrib"].values())
            acts.append(0.5 if s >= BAND else -0.5 if k is not None and s <= -k else 0.0)
        out[w["name"]] = acts
    return out


def summarise(windows, acts):
    res = {w["name"]: simulate(w, acts[w["name"]]) for w in windows}
    hits = sum(r["direction_accuracy"] * r["directional_days"] for r in res.values() if r["directional_days"])
    n = sum(r["directional_days"] for r in res.values())
    return {"mean_return": float(np.mean([r["total_return"] for r in res.values()])),
            "mean_sharpe": float(np.mean([r["sharpe"] for r in res.values()])),
            "accuracy": float(hits / n), "directional_days": int(n),
            "windows": {k: v["total_return"] for k, v in res.items()}}


def main():
    prices = load_prices()
    windows = [load_window(n, prices) for n in [*DEV_WINDOWS, *WINDOWS]]
    by_name = {w["name"]: w for w in windows}
    dev, test = [by_name[n] for n in DEV_WINDOWS], [by_name[n] for n in WINDOWS]
    grid = {k: actions_all(windows, k) for k in KS}
    rows = {k: {"dev": summarise(dev, a), "test": summarise(test, a)} for k, a in grid.items()}
    best = max(KS, key=lambda k: (round(rows[k]["dev"]["mean_return"], 6), rows[k]["dev"]["mean_sharpe"]))
    v1 = {s: summarise(ws, {w["name"]: [r["saved_action"] for r in w["rows"]] for w in ws}) for s, ws in (("dev", dev), ("test", test))}
    pairs = lambda ws: [(np.array(simulate(w, grid[best][w["name"]], daily=True)["daily_returns"]), sig.ct_returns(w["name"])) for w in ws]
    boot = {"dev": sig.paired_bootstrap(pairs(dev)), "test": sig.paired_bootstrap(pairs(test)),
            "pooled": sig.paired_bootstrap(pairs(dev + test))}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "result.json").write_text(json.dumps({"selected_k": best, "grid": {str(k): v for k, v in rows.items()},
                                                 "eval_v1": v1, "selected_minus_ct_full": boot}, indent=2))
    name = lambda k: "never SELL" if k is None else f"SELL if S<=-{k:.2f}"
    print(f"{'rule (+ arbiter on conflict days)':34s} {'dev ret':>8s} {'dev acc':>8s} | {'test ret':>8s} {'test acc':>8s}")
    for k in KS:
        d, t = rows[k]["dev"], rows[k]["test"]
        print(f"  {name(k):32s} {d['mean_return'] * 100:+7.2f}% {d['accuracy'] * 100:6.1f}%  | {t['mean_return'] * 100:+7.2f}% "
              f"{t['accuracy'] * 100:6.1f}%" + ("   <- selected on dev" if k == best else ""))
    print(f"  {'eval-v1':32s} {v1['dev']['mean_return'] * 100:+7.2f}% {v1['dev']['accuracy'] * 100:6.1f}%  | "
          f"{v1['test']['mean_return'] * 100:+7.2f}% {v1['test']['accuracy'] * 100:6.1f}%")
    print("  references: CT full dev +11.95% test +5.71% | buy and hold dev +11.85% test +7.74%")
    print("Selected minus CryptoTrade full (paired block bootstrap)")
    for s, r in boot.items():
        print(f"  {s:7s} {r['diff'] * 100:+6.2f}  CI [{r['ci95'][0] * 100:+6.2f}, {r['ci95'][1] * 100:+6.2f}]  p={r['p']:.3f}")
    print("per window (selected):", {k: round(v * 100, 2) for s in ("dev", "test") for k, v in rows[best][s]["windows"].items()})


if __name__ == "__main__":
    main()
