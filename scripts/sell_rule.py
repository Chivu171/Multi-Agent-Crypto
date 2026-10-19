"""Asymmetric SELL rule (no LLM calls): a SELL needs stronger evidence than a BUY.

Rationale fixed before looking at results: the environment has no short selling and
charges fees, so a wrong SELL in a rally gives up the gain on the coins sold, while
a wrong BUY only risks the cash spent. BUY stays at S_final >= +0.05; a SELL needs
S_final <= -k and, optionally, at least m of the three agents on the SELL side
(after Debate). k = inf means the system never sells (long-only reference).

    python scripts/sell_rule.py select     # grid on the dev windows only -> selected.json
    python scripts/sell_rule.py evaluate   # the selected rule on the test windows, once
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from baselines.cryptotrade.env import DEV_WINDOWS, WINDOWS, load_prices  # noqa: E402
from scripts.trend_variants import check_reproduction, load_window, simulate  # noqa: E402

from scripts.asset import RUNS, out_dir  # noqa: E402

OUT = out_dir("outputs/sell_rule")
BAND = 0.05
GRID = [{"k": k, "m": m} for k in (0.05, 0.10, 0.15, 0.20, 0.30) for m in (0, 2)] + [{"k": None, "m": 0}]
REFERENCES = {"ct_full": "agent_paper_full__google_gemma-4-26b-a4b-qat"}


def actions(window, k, m):
    out = []
    for row in window["rows"]:
        if not row["ok"]:
            out.append(0.0)
            continue
        s = sum(row["contrib"].values())
        sellers = sum(c < 0 for c in row["contrib"].values())
        if s >= BAND:
            out.append(0.5)
        elif k is not None and s <= -k and sellers >= m:
            out.append(-0.5)
        else:
            out.append(0.0)
    return out


def score(windows, k, m):
    res = {w["name"]: simulate(w, actions(w, k, m)) for w in windows}
    return {"k": k, "m": m, "mean_return": float(np.mean([r["total_return"] for r in res.values()])),
            "mean_sharpe": float(np.mean([r["sharpe"] for r in res.values()])),
            "sells": int(sum(a < 0 for w in windows for a in actions(w, k, m))), "windows": res}


def references(names):
    out = {}
    for name, run in REFERENCES.items():
        rets = [json.loads((RUNS / w / run / "result.json").read_text())["total_return"] for w in names]
        out[name] = float(np.mean(rets))
    rules = [{r["strategy"]: r["total_return"] for r in json.loads((RUNS / w / "rules.json").read_text())} for w in names]
    out["buy_and_hold"] = float(np.mean([r["buy_and_hold"] for r in rules]))
    return out


def label(c):
    return ("never SELL" if c["k"] is None else f"SELL if S<=-{c['k']:.2f}") + (f", >={c['m']} sellers" if c["m"] else "")


def show(title, rows, refs):
    print(title)
    for r in rows:
        per = "  ".join(f"{w}: {x['total_return'] * 100:+6.2f}%" for w, x in r["windows"].items())
        print(f"  {label(r):28s} mean {r['mean_return'] * 100:+6.2f}%  sharpe {r['mean_sharpe']:+.3f}  sells {r['sells']:3d} | {per}")
    print("  references: " + "  ".join(f"{k} {v * 100:+.2f}%" for k, v in refs.items()))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("step", choices=("select", "evaluate"))
    args = parser.parse_args()
    prices = load_prices()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.step == "select":
        windows = [load_window(n, prices) for n in DEV_WINDOWS]
        check_reproduction(windows)
        rows = [score(windows, **c) for c in GRID]
        best = max(rows, key=lambda r: (round(r["mean_return"], 6), r["mean_sharpe"]))
        refs = references(DEV_WINDOWS)
        (OUT / "selected.json").write_text(json.dumps({"selected_on": list(DEV_WINDOWS), "selected": best,
                                                       "grid": rows, "references": refs}, indent=2))
        show("DEV (selection)", rows, refs)
        print(f"selected: {label(best)}")
        return
    selected = json.loads((OUT / "selected.json").read_text())["selected"]
    windows = [load_window(n, prices) for n in WINDOWS]
    check_reproduction(windows)
    result = {"evaluated_on": list(WINDOWS), "eval_v1": score(windows, 0.05, 0),
              "selected": score(windows, selected["k"], selected["m"]), "references": references(WINDOWS),
              "grid_after_selection": [score(windows, **c) for c in GRID]}
    (OUT / "test_result.json").write_text(json.dumps(result, indent=2))
    show("TEST (selected rule, evaluated once)", [result["eval_v1"], result["selected"]], result["references"])
    show("TEST, whole grid (robustness only, not used for selection)", result["grid_after_selection"], {})


if __name__ == "__main__":
    main()
