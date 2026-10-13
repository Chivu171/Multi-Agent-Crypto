"""Offline analysis of saved eval-v1 days (no LLM calls).

1. Direction accuracy of each agent per trend regime (up / flat / down), dev vs test.
2. Does a larger |S_final| mean a more accurate day?
3. Robustness of the dev selection: leave one dev window out, and the neighbours of the chosen filter.

    python scripts/agent_regime_analysis.py
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from baselines.cryptotrade.env import DEV_WINDOWS, WINDOWS, load_prices  # noqa: E402
from scripts.trend_variants import (  # noqa: E402
    AGENTS, REGIMES, RUN_NAME, RUNS, TREND_GRID, multiplier_grid, regime, score,
)
from scripts.trend_variants import load_window  # noqa: E402

TREND = dict(ma=50, lookback=20, band=0.05)  # regime definition chosen on dev in selected.json
S_BUCKETS = (0.05, 0.1, 0.2, 0.3, np.inf)


def day_records(name, prices):
    """One record per ok day: per-agent direction, S_final, regime, next-open move."""
    start, end = {**WINDOWS, **DEV_WINDOWS}[name]
    index = {d["date"]: i for i, d in enumerate(prices)}
    opens = np.array([d["open"] for d in prices])
    dates = [d["date"] for d in prices if start <= d["date"] <= end]
    out = []
    for date, nxt in zip(dates[:-1], dates[1:]):
        day = json.loads((RUNS / name / RUN_NAME / "days" / f"{date}.json").read_text())
        if day.get("status") != "ok":
            continue
        i = index[date]
        out.append({"regime": regime(opens, i, **TREND), "up_next": opens[index[nxt]] > opens[i],
                    "S_final": day["mediator"]["S_final"],
                    "dir": {d["agent_id"]: d["direction"] for d in day["mediator"]["details"]}})
    return out


def agent_table(records):
    table = {}
    for agent in AGENTS:
        for reg in (*REGIMES, "all"):
            hits = [(r["dir"].get(agent, 0) > 0) == r["up_next"] for r in records
                    if r["dir"].get(agent, 0) != 0 and reg in (r["regime"], "all")]
            table[(agent, reg)] = (np.mean(hits) if hits else None, len(hits))
    return table


def s_table(records):
    rows, lo = [], 0.0
    for hi in S_BUCKETS:
        hits = [(r["S_final"] > 0) == r["up_next"] for r in records if lo <= abs(r["S_final"]) < hi and r["S_final"]]
        rows.append((lo, hi, np.mean(hits) if hits else None, len(hits)))
        lo = hi
    return rows


def fmt(acc, n):
    return f"{acc * 100:5.1f}% ({n:3d})" if acc is not None else f"{'-':>5s}  ({n:3d})"


def print_agents(title, records):
    t = agent_table(records)
    counts = {reg: sum(r["regime"] == reg for r in records) for reg in REGIMES}
    print(f"\n{title}  days per regime {counts}")
    print(f"  {'agent':16s}" + "".join(f"{reg:>14s}" for reg in (*REGIMES, "all")))
    for agent in AGENTS:
        print(f"  {agent:16s}" + "".join(f"{fmt(*t[(agent, reg)]):>14s}" for reg in (*REGIMES, "all")))
    print("  |S_final| bucket -> direction accuracy (days)")
    for lo, hi, acc, n in s_table(records):
        print(f"    [{lo:.2f}, {hi:.2f})  {fmt(acc, n)}")


def leave_one_out(prices):
    """Re-run the dev selection on two dev windows; score the choice on the held-out one."""
    dev = {n: load_window(n, prices) for n in DEV_WINDOWS}
    key = lambda s: (s["mean_return"], s["mean_sharpe"])  # noqa: E731
    print("\nLeave one dev window out (select on 2, score on the 3rd), return on held-out vs eval-v1")
    for held in dev:
        train = [w for n, w in dev.items() if n != held]
        f = max(TREND_GRID, key=lambda t: key(score(train, trend=t, use_filter=True)))
        best_w = max(((t, m) for t in TREND_GRID for m in multiplier_grid()),
                     key=lambda tm: key(score(train, trend=tm[0], mult=tm[1])))
        base = score([dev[held]])["mean_return"]
        fr = score([dev[held]], trend=f, use_filter=True)["mean_return"]
        wr = score([dev[held]], trend=best_w[0], mult=best_w[1])["mean_return"]
        print(f"  held out {held:12s} eval-v1 {base * 100:+6.2f}%  filter {fr * 100:+6.2f}%  weights {wr * 100:+6.2f}%")


def filter_neighbours(prices):
    dev = [load_window(n, prices) for n in DEV_WINDOWS]
    test = [load_window(n, prices) for n in WINDOWS]
    print("\nFilter over the whole trend grid (dev mean / test mean return)")
    for t in TREND_GRID:
        d, s = score(dev, trend=t, use_filter=True), score(test, trend=t, use_filter=True)
        print(f"  ma {t['ma']:2d} lookback {t['lookback']:2d} band {t['band']:.2f}   "
              f"dev {d['mean_return'] * 100:+6.2f}%   test {s['mean_return'] * 100:+6.2f}%")


def main():
    prices = load_prices()
    dev = [r for n in DEV_WINDOWS for r in day_records(n, prices)]
    test = [r for n in WINDOWS for r in day_records(n, prices)]
    print(f"Regime: {TREND}; accuracy = share of non-neutral calls matching the next open-to-open move")
    print_agents("DEV", dev)
    print_agents("TEST", test)
    leave_one_out(prices)
    filter_neighbours(prices)


if __name__ == "__main__":
    main()
