"""Offline trend-aware variants of our system (no LLM calls).

Re-aggregates the saved Mediator contributions of each day with three changes:
- regime-dependent agent multipliers: S = sum_i contribution_i * m[regime][agent_i];
- a trend filter that turns a SELL in an up-trend / a BUY in a down-trend into NEUTRAL;
- signal-strength position sizing: action = clip(S / scale, -1, 1) instead of a fixed +-0.5.
The regime of day D uses only opens up to D's open (what the agents see at decision time).

Two steps keep the test periods out of tuning:
    python scripts/trend_variants.py select     # grid search on the dev windows only -> selected.json
    python scripts/trend_variants.py evaluate   # applies selected.json to the test windows, once
    python scripts/trend_variants.py prespecified  # sizing with the existing STRONG floor (0.5), no tuning
"""
import argparse
import itertools
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from baselines.cryptotrade.env import (  # noqa: E402
    DEV_WINDOWS, EX_RATE, GAS_FEE, STARTING_CASH_RATIO, STARTING_NET_WORTH, WINDOWS, load_prices, sharpe,
)
from baselines.cryptotrade.ours import ACTION, signal_of  # noqa: E402
from utils.thresholds import SIGNAL_STRONG_INTENSITY_FLOOR  # noqa: E402

RUNS = Path("outputs/baselines/cryptotrade")
RUN_NAME = "ours__google_gemma-4-26b-a4b-qat"
OUT = Path("outputs/trend_variants")
AGENTS = ("Market_Agent", "Financial_Agent", "Sentiment_Agent")
REGIMES = ("up", "flat", "down")

# Small grids on purpose: ~150 dev days cannot support many free parameters.
TREND_GRID = [dict(ma=ma, lookback=lb, band=band) for ma in (20, 50) for lb in (10, 20, 30) for band in (0.0, 0.03, 0.05)]
MULTIPLIERS = (0.0, 1.0, 2.0)  # for Financial and Sentiment per regime; Market stays 1
SIZING_SCALES = (0.1, 0.2, 0.3, 0.5)  # |S| at which the full position (1.0) is reached


def regime(opens, i, ma, lookback, band):
    """'up' / 'down' when price and its `lookback`-day return agree on the trend, else 'flat'."""
    price = opens[i]
    trend_return = price / opens[i - lookback] - 1
    above = price > opens[i - ma + 1: i + 1].mean()
    if above and trend_return > band:
        return "up"
    if not above and trend_return < -band:
        return "down"
    return "flat"


def load_window(name, prices):
    start, end = {**WINDOWS, **DEV_WINDOWS}[name]
    days_dir = RUNS / name / RUN_NAME / "days"
    index = {d["date"]: i for i, d in enumerate(prices)}
    opens = np.array([d["open"] for d in prices])
    dates = [d["date"] for d in prices if start <= d["date"] <= end]
    rows = []
    for date in dates[:-1]:  # the last date only supplies the final open
        path = days_dir / f"{date}.json"
        day = json.loads(path.read_text()) if path.exists() else {"status": "missing"}
        contrib = {a: 0.0 for a in AGENTS}
        if day.get("status") == "ok":
            for d in day["mediator"]["details"]:
                contrib[d["agent_id"]] = d["contribution"]
        rows.append({"date": date, "i": index[date], "ok": day.get("status") == "ok",
                     "saved_action": day.get("action", 0.0), "contrib": contrib})
    return {"name": name, "rows": rows, "opens": opens, "last_open": opens[index[dates[-1]]]}


def simulate(window, actions):
    """Same arithmetic as TradingEnv.step, without loading news each step."""
    opens, rows = window["opens"], window["rows"]
    cash = STARTING_NET_WORTH * STARTING_CASH_RATIO
    coin = (STARTING_NET_WORTH - cash) / opens[rows[0]["i"]]
    last, returns, directional, correct = STARTING_NET_WORTH, [], 0, 0
    for k, (row, action) in enumerate(zip(rows, actions)):
        price = opens[row["i"]]
        if action < 0 and coin > 0:
            coin_diff = -action * coin
            cash_diff = coin_diff * price
            coin -= coin_diff
            cash += cash_diff
            cash -= GAS_FEE * price + cash_diff * EX_RATE
        if action > 0 and cash > 0:
            cash_diff = action * cash
            cash -= cash_diff
            coin += cash_diff / price
            cash -= GAS_FEE * price + cash_diff * EX_RATE
        next_open = opens[rows[k + 1]["i"]] if k + 1 < len(rows) else window["last_open"]
        worth = cash + coin * next_open
        returns.append(worth / last - 1)
        last = worth
        if action:
            directional += 1
            correct += (action > 0) == (next_open > price)
    return {"total_return": last / STARTING_NET_WORTH - 1, "sharpe": sharpe(returns),
            "direction_accuracy": correct / directional if directional else None, "directional_days": directional}


def actions_for(window, trend=None, mult=None, use_filter=False, sizing=None):
    out = []
    for row in window["rows"]:
        if not row["ok"]:
            out.append(0.0)
            continue
        reg = regime(window["opens"], row["i"], **trend) if trend else "flat"
        m = (mult or {}).get(reg, {})
        s_final = sum(c * m.get(a, 1.0) for a, c in row["contrib"].items())
        signal = signal_of(s_final)
        if use_filter and ((reg == "up" and signal == "SELL") or (reg == "down" and signal == "BUY")):
            signal = "NEUTRAL"
        if sizing and signal != "NEUTRAL":
            out.append(float(np.clip(s_final / sizing, -1.0, 1.0)))
        else:
            out.append(ACTION[signal])
    return out


def score(windows, **kw):
    results = {w["name"]: simulate(w, actions_for(w, **kw)) for w in windows}
    rets = [r["total_return"] for r in results.values()]
    shs = [r["sharpe"] for r in results.values()]
    return {"mean_return": float(np.mean(rets)), "mean_sharpe": float(np.mean(shs)), "windows": results}


def multiplier_grid():
    for combo in itertools.product(MULTIPLIERS, repeat=2 * len(REGIMES)):
        yield {reg: {"Financial_Agent": combo[2 * k], "Sentiment_Agent": combo[2 * k + 1]}
               for k, reg in enumerate(REGIMES)}


def check_reproduction(windows):
    """Unchanged aggregation must reproduce the saved decisions exactly."""
    for w in windows:
        assert actions_for(w) == [r["saved_action"] for r in w["rows"]], f"saved actions differ in {w['name']}"


def regime_counts(windows, trend):
    counts = {r: 0 for r in REGIMES}
    for w in windows:
        for row in w["rows"]:
            counts[regime(w["opens"], row["i"], **trend)] += 1
    return counts


def select(prices):
    windows = [load_window(n, prices) for n in DEV_WINDOWS]
    missing = {w["name"]: sum(not r["ok"] for r in w["rows"]) for w in windows}
    check_reproduction(windows)
    key = lambda s: (s["mean_return"], s["mean_sharpe"])  # noqa: E731
    baseline = score(windows)
    best_filter = max(({"trend": t, **score(windows, trend=t, use_filter=True)} for t in TREND_GRID), key=key)
    best_weights, best_both = None, None
    for t in TREND_GRID:
        for mult in multiplier_grid():
            s = {"trend": t, "mult": mult, **score(windows, trend=t, mult=mult)}
            best_weights = s if best_weights is None or key(s) > key(best_weights) else best_weights
            s2 = {"trend": t, "mult": mult, **score(windows, trend=t, mult=mult, use_filter=True)}
            best_both = s2 if best_both is None or key(s2) > key(best_both) else best_both
    best_sizing = max(({"sizing": k, **score(windows, sizing=k)} for k in SIZING_SCALES), key=key)
    best_all = max(({"trend": best_both["trend"], "mult": best_both["mult"], "sizing": k,
                     **score(windows, trend=best_both["trend"], mult=best_both["mult"], use_filter=True, sizing=k)}
                    for k in SIZING_SCALES), key=key)
    selected = {"selected_on": list(DEV_WINDOWS), "not_ok_days": missing,
                "baseline_eval_v1": baseline, "filter": best_filter, "weights": best_weights, "both": best_both,
                "sizing": best_sizing, "both_sizing": best_all,
                "regime_counts": {k: regime_counts(windows, v["trend"]) for k, v in
                                  (("filter", best_filter), ("weights", best_weights), ("both", best_both))}}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "selected.json").write_text(json.dumps(selected, indent=2))
    print_table("DEV (selection)", selected)


def evaluate(prices):
    selected = json.loads((OUT / "selected.json").read_text())
    windows = [load_window(n, prices) for n in WINDOWS]
    check_reproduction(windows)
    result = {"evaluated_on": list(WINDOWS), "baseline_eval_v1": score(windows),
              "filter": {"trend": selected["filter"]["trend"],
                         **score(windows, trend=selected["filter"]["trend"], use_filter=True)},
              "weights": {"trend": selected["weights"]["trend"], "mult": selected["weights"]["mult"],
                          **score(windows, trend=selected["weights"]["trend"], mult=selected["weights"]["mult"])},
              "both": {"trend": selected["both"]["trend"], "mult": selected["both"]["mult"],
                       **score(windows, trend=selected["both"]["trend"], mult=selected["both"]["mult"],
                               use_filter=True)},
              "sizing": {"sizing": selected["sizing"]["sizing"], **score(windows, sizing=selected["sizing"]["sizing"])},
              "both_sizing": {k: selected["both_sizing"][k] for k in ("trend", "mult", "sizing")}}
    b = result["both_sizing"]
    b.update(score(windows, trend=b["trend"], mult=b["mult"], use_filter=True, sizing=b["sizing"]))
    (OUT / "test_result.json").write_text(json.dumps(result, indent=2))
    print_table("TEST (selected config, evaluated once)", result)


def prespecified(prices):
    """Sizing rule fixed before looking at any result: full position at the existing STRONG floor."""
    windows = [load_window(n, prices) for n in WINDOWS]
    check_reproduction(windows)
    k = SIGNAL_STRONG_INTENSITY_FLOOR
    result = {"evaluated_on": list(WINDOWS), "baseline_eval_v1": score(windows),
              "sizing": {"sizing": k, **score(windows, sizing=k)}}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "prespecified_sizing_test.json").write_text(json.dumps(result, indent=2))
    print_table(f"TEST, prespecified sizing scale {k} (no tuning)", result)


def print_table(title, res):
    print(title)
    for name in ("baseline_eval_v1", "filter", "weights", "both", "sizing", "both_sizing"):
        if name not in res:
            continue
        s = res[name]
        per = "  ".join(f"{w}: {r['total_return'] * 100:+6.2f}%" for w, r in s["windows"].items())
        print(f"  {name:17s} mean {s['mean_return'] * 100:+6.2f}%  sharpe {s['mean_sharpe']:+.3f}  | {per}")
        extra = {k: s[k] for k in ("trend", "mult", "sizing") if k in s}
        if extra:
            print(f"  {'':17s} {extra}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("step", choices=("select", "evaluate", "prespecified", "check"))
    args = parser.parse_args()
    prices = load_prices()
    if args.step == "check":  # reproduction check on the windows that already have runs
        names = [n for n in {**WINDOWS, **DEV_WINDOWS} if (RUNS / n / RUN_NAME / "days").exists()]
        for n in names:
            w = load_window(n, prices)
            check_reproduction([w])
            print(n, {k: round(v, 4) if isinstance(v, float) else v for k, v in simulate(w, actions_for(w)).items()})
        return
    {"select": select, "evaluate": evaluate, "prespecified": prespecified}[args.step](prices)


if __name__ == "__main__":
    main()
