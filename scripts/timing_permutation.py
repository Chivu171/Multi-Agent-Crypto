"""Do returns come from WHEN a strategy trades or only from HOW MUCH it holds? (no LLM calls)

For each window, the strategy's own actions are shuffled across its trading days
(same actions, random order) and replayed through the same environment arithmetic.
A strategy with timing skill should beat most of its shuffles; a strategy whose
return comes from its mix of BUY/SELL sizes alone sits in the middle of them.
The statistic for a set of windows is the mean return over the windows; each
shuffle reorders every window independently. p (one-sided) = share of shuffles
whose mean return is at least the actual one.

Also: paired block bootstrap of the never-SELL rule (scripts/sell_rule.py) against
CryptoTrade full, with the functions of scripts/significance.py.

    python scripts/timing_permutation.py   # -> outputs/timing_permutation/result.json
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import scripts.significance as sig  # noqa: E402
from baselines.cryptotrade.env import DEV_WINDOWS, WINDOWS, load_prices  # noqa: E402
from scripts.sell_rule import actions as sell_rule_actions  # noqa: E402
from scripts.trend_variants import load_window, simulate  # noqa: E402

from scripts.asset import RUNS, out_dir  # noqa: E402

OUT = out_dir("outputs/timing_permutation")
SHUFFLES, SEED = 5_000, 0
SETS = {"dev": list(DEV_WINDOWS), "test": list(WINDOWS), "pooled": [*DEV_WINDOWS, *WINDOWS]}


def strategy_actions(window, name):
    rows = window["rows"]
    if name == "ours_eval_v1":
        return [r["saved_action"] for r in rows]
    if name == "ours_never_sell":
        return sell_rule_actions(window, None, 0)
    steps = json.loads((RUNS / window["name"] / sig.CT_FULL / "steps.json").read_text())
    by_date = {s["date"]: s["action"] for s in steps}
    return [by_date[r["date"]] for r in rows]


def check_ct(window):
    """Replaying CryptoTrade's actions must give its reported return."""
    reported = json.loads((RUNS / window["name"] / sig.CT_FULL / "result.json").read_text())["total_return"]
    replayed = simulate(window, strategy_actions(window, "ct_full"))["total_return"]
    assert abs(reported - replayed) < 1e-9, (window["name"], reported, replayed)


def permutation(windows, name):
    acts = [np.array(strategy_actions(w, name)) for w in windows]
    actual = np.mean([simulate(w, a)["total_return"] for w, a in zip(windows, acts)])
    rng, shuffled = np.random.default_rng(SEED), np.empty(SHUFFLES)
    for k in range(SHUFFLES):
        shuffled[k] = np.mean([simulate(w, rng.permutation(a))["total_return"] for w, a in zip(windows, acts)])
    return {"actual": float(actual), "shuffled_mean": float(shuffled.mean()),
            "shuffled_ci95": [float(np.percentile(shuffled, 2.5)), float(np.percentile(shuffled, 97.5))],
            "percentile": float((shuffled < actual).mean()), "p_one_sided": float((shuffled >= actual).mean())}


def main():
    prices = load_prices()
    windows = {n: load_window(n, prices) for n in SETS["pooled"]}
    for w in windows.values():
        check_ct(w)
    result = {"shuffles": SHUFFLES, "seed": SEED, "permutation": {}, "never_sell_vs_ct_full": {}}
    for s, names in SETS.items():
        for name in ("ours_eval_v1", "ours_never_sell", "ct_full"):
            result["permutation"].setdefault(s, {})[name] = permutation([windows[n] for n in names], name)
        pairs = [(np.array(simulate(windows[n], strategy_actions(windows[n], "ours_never_sell"), daily=True)["daily_returns"]),
                  sig.ct_returns(n)) for n in names]
        result["never_sell_vs_ct_full"][s] = sig.paired_bootstrap(pairs)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "result.json").write_text(json.dumps(result, indent=2))
    print("Actual mean return vs the same actions in random order")
    for s, res in result["permutation"].items():
        for name, r in res.items():
            print(f"  {s:7s} {name:16s} actual {r['actual'] * 100:+6.2f}%  shuffled {r['shuffled_mean'] * 100:+6.2f}% "
                  f"[{r['shuffled_ci95'][0] * 100:+6.2f}, {r['shuffled_ci95'][1] * 100:+6.2f}]  "
                  f"beats {r['percentile'] * 100:5.1f}% of shuffles  p={r['p_one_sided']:.3f}")
    print("Never-SELL minus CryptoTrade full (paired block bootstrap)")
    for s, r in result["never_sell_vs_ct_full"].items():
        print(f"  {s:7s} {r['diff'] * 100:+6.2f}  CI [{r['ci95'][0] * 100:+6.2f}, {r['ci95'][1] * 100:+6.2f}]  p={r['p']:.3f}")


if __name__ == "__main__":
    main()
