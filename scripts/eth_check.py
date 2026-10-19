"""Pre-registered ETH analysis (docs/eth_preregistration.md), no LLM calls.

    python scripts/eth_check.py   # -> outputs/eth_check/result.json

H1: the long-run reliability arbiter (fixed configuration) has a higher direction
accuracy than eval-v1 on all trading days, pooled over the six ETH windows; the 95%
interval of the difference comes from a 5-day block bootstrap of the days.
Secondary results are descriptive; every configuration is fixed from BTC.
"""
import os

os.environ["ASSET"] = "eth"  # before anything reads the asset

import json  # noqa: E402
import re  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scripts.horizon_analysis as ha  # noqa: E402
import scripts.reliability_arbiter as ra  # noqa: E402
import scripts.significance as sig  # noqa: E402
import scripts.timing_permutation as tp  # noqa: E402
from baselines.cryptotrade.env import DEV_WINDOWS, WINDOWS, load_prices  # noqa: E402
from scripts.asset import RUNS  # noqa: E402
from scripts.sell_rule import actions as sell_rule_actions  # noqa: E402
from scripts.trend_variants import AGENTS, RUN_NAME, check_reproduction, load_window, simulate  # noqa: E402

OUT = Path("outputs/eth_check")
PRIOR, BLOCK, RESAMPLES, SEED = 5, 5, 10_000, 0
SETS = {"dev": list(DEV_WINDOWS), "test": list(WINDOWS), "pooled": [*DEV_WINDOWS, *WINDOWS]}


def arbiter_days(windows):
    """Per window, in time order: (eval-v1 call, arbiter call, went up) for every trading day."""
    right, seen, out = {a: 0 for a in AGENTS}, {a: 0 for a in AGENTS}, {}
    for w in sorted(windows, key=lambda w: w["rows"][0]["date"]):
        opens, rows, days = w["opens"], w["rows"], []
        for k, row in enumerate(rows):
            nxt = opens[rows[k + 1]["i"]] if k + 1 < len(rows) else w["last_open"]
            up = bool(nxt > opens[row["i"]])
            v1 = int(np.sign(row["saved_action"]))
            dirs = {a: int(np.sign(c)) for a, c in row["contrib"].items()}
            call = v1
            if row["ok"] and 1 in dirs.values() and -1 in dirs.values():
                rel = {a: (right[a] + PRIOR) / (seen[a] + 2 * PRIOR) for a in AGENTS}
                call = int(np.sign(sum(dirs[a] * (rel[a] - 0.5) for a in AGENTS)))
                for a in AGENTS:
                    if dirs[a]:
                        seen[a] += 1
                        right[a] += (dirs[a] > 0) == up
            days.append((v1, call, up))
        out[w["name"]] = np.array(days)
    return out


def accuracy(days, col):
    calls, up = days[:, col], days[:, 2].astype(bool)
    mask = calls != 0
    return float(np.mean((calls[mask] > 0) == up[mask])), int(mask.sum())


def h1(days_by_window, names):
    parts = [days_by_window[n] for n in names]
    alld = np.concatenate(parts)
    (a1, n1), (a2, n2) = accuracy(alld, 0), accuracy(alld, 1)
    rng, diffs = np.random.default_rng(SEED), np.empty(RESAMPLES)
    for k in range(RESAMPLES):
        sample = np.concatenate([p[sig.block_indices(len(p), rng)] for p in parts])
        diffs[k] = accuracy(sample, 1)[0] - accuracy(sample, 0)[0]
    return {"eval_v1": {"accuracy": a1, "calls": n1}, "arbiter": {"accuracy": a2, "calls": n2},
            "diff": a2 - a1, "ci95": [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))],
            "supported": bool(np.percentile(diffs, 2.5) > 0)}


def market_sell_in_uptrend(names):
    rows = []
    for n in names:
        for path in sorted((RUNS / n / RUN_NAME / "days").glob("*.json")):
            d = json.loads(path.read_text())
            if d.get("status") != "ok":
                continue
            m = next(s for s in d["specialists"] if s["agent_id"] == "Market_Agent")
            txt = m["evidence_chunks"][0]["content"]
            g = lambda k: re.search(k + r": ([\w.]+)", txt).group(1)
            price = float(re.findall(r"Open \S+: ([\d.]+)", txt)[-1])
            if price > float(g("EMA20 of daily opens")) and price > float(g("EMA50 of daily opens")):
                rows.append((m["signal"], g("short_long_ma_signal") == "sell" and g("macd_signal") == "sell", d["signal"]))
    return {"uptrend_days": len(rows), "both_labels_sell": float(np.mean([r[1] for r in rows])),
            "market_sell": float(np.mean([r[0] == "SELL" for r in rows])),
            "market_buy": float(np.mean([r[0] == "BUY" for r in rows])),
            "final_sell": float(np.mean([r[2] == "SELL" for r in rows]))}


def main():
    prices = load_prices()
    windows = {n: load_window(n, prices) for n in SETS["pooled"]}
    check_reproduction(list(windows.values()))
    res = {"preregistration": "docs/eth_preregistration.md (tag eth-prereg)"}

    days = arbiter_days(list(windows.values()))
    res["H1"] = {s: h1(days, names) for s, names in SETS.items()}
    arb_returns = {}
    for n, w in windows.items():
        arb_returns[n] = simulate(w, [0.5 * c for c in days[n][:, 1]])["total_return"]
    res["H1_returns"] = {s: {"eval_v1": float(np.mean([simulate(windows[n], [r["saved_action"] for r in windows[n]["rows"]])["total_return"] for n in names])),
                             "arbiter": float(np.mean([arb_returns[n] for n in names]))} for s, names in SETS.items()}

    rules = {n: {r["strategy"]: r["total_return"] for r in json.loads((RUNS / n / "rules.json").read_text())} for n in windows}
    ct = {n: json.loads((RUNS / n / sig.CT_FULL / "result.json").read_text())["total_return"] for n in windows}
    ours = {n: simulate(w, [r["saved_action"] for r in w["rows"]])["total_return"] for n, w in windows.items()}
    never = {n: simulate(w, sell_rule_actions(w, None, 0))["total_return"] for n, w in windows.items()}
    res["returns"] = {n: {"ours": ours[n], "ct_full": ct[n], "buy_and_hold": rules[n]["buy_and_hold"], "never_sell": never[n]}
                      for n in windows}
    res["ours_vs_ct_full"] = {s: sig.paired_bootstrap([(sig.ours_returns(n, prices), sig.ct_returns(n)) for n in names])
                              for s, names in SETS.items()}
    res["never_sell_vs_ct_full"] = {s: sig.paired_bootstrap(
        [(np.array(simulate(windows[n], sell_rule_actions(windows[n], None, 0), daily=True)["daily_returns"]), sig.ct_returns(n))
         for n in names]) for s, names in SETS.items()}

    acts = [s["action"] for n in windows for s in json.loads((RUNS / n / sig.CT_FULL / "steps.json").read_text())]
    res["ct_buy_share"] = {"buy": int(sum(a > 0 for a in acts)), "sell": int(sum(a < 0 for a in acts)),
                           "share": float(sum(a > 0 for a in acts) / sum(a != 0 for a in acts))}

    wc = {n: ha.calls(n, prices) for n in windows}
    opens = np.array([d["open"] for d in prices])
    res["horizons_pooled"] = {strat: {h: ha.analyse([ha.outcomes(wc[n][strat], opens, h) for n in windows], h) for h in ha.HORIZONS}
                              for strat in (*AGENTS, "ours_final", "ct_full")}
    res["timing_pooled"] = {name: tp.permutation(list(windows.values()), name) for name in ("ours_eval_v1", "ct_full")}
    res["market_in_uptrend"] = market_sell_in_uptrend(list(windows))
    ra.OUT.mkdir(parents=True, exist_ok=True)
    ra.conflicts(prices)
    res["conflict_rules"] = json.loads((ra.OUT / "conflict_rules.json").read_text())

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "result.json").write_text(json.dumps(res, indent=2))
    print("\nH1 (direction accuracy, arbiter vs eval-v1; supported if CI lower bound > 0)")
    for s, r in res["H1"].items():
        print(f"  {s:6s} eval-v1 {r['eval_v1']['accuracy'] * 100:.1f}% ({r['eval_v1']['calls']})  arbiter {r['arbiter']['accuracy'] * 100:.1f}% "
              f"({r['arbiter']['calls']})  diff {r['diff'] * 100:+.1f} CI [{r['ci95'][0] * 100:+.1f}, {r['ci95'][1] * 100:+.1f}]  "
              f"supported={r['supported']} | mean return v1 {res['H1_returns'][s]['eval_v1'] * 100:+.2f}% arbiter {res['H1_returns'][s]['arbiter'] * 100:+.2f}%")
    print("\nReturns per window (ours / CT full / buy and hold / never SELL)")
    for n, r in res["returns"].items():
        print(f"  {n:12s} " + "  ".join(f"{k} {v * 100:+6.2f}%" for k, v in r.items()))
    for s, names in SETS.items():
        m = {k: np.mean([res["returns"][n][k] for n in names]) * 100 for k in ("ours", "ct_full", "buy_and_hold", "never_sell")}
        print(f"  mean {s:7s} " + "  ".join(f"{k} {v:+6.2f}%" for k, v in m.items()))
    for key in ("ours_vs_ct_full", "never_sell_vs_ct_full"):
        print(key, {s: f"{r['diff'] * 100:+.2f} [{r['ci95'][0] * 100:+.2f},{r['ci95'][1] * 100:+.2f}] p={r['p']:.3f}" for s, r in res[key].items()})
    print("CT buy share", res["ct_buy_share"])
    print("Horizon edge pooled:", {s: {h: round(r['edge'] * 100, 1) for h, r in v.items()} for s, v in res["horizons_pooled"].items()})
    print("Timing pooled:", {k: (round(v['actual'] * 100, 2), round(v['shuffled_mean'] * 100, 2), round(v['p_one_sided'], 3)) for k, v in res["timing_pooled"].items()})
    print("Market in uptrend:", res["market_in_uptrend"])


if __name__ == "__main__":
    main()
