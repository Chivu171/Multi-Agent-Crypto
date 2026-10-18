"""Conflict arbiter that trusts agents by their past record in conflicts (no LLM calls).

A conflict day has at least one BUY and one SELL among the three specialists. Each
agent's record counts how often its call was right on PAST conflict days of the same
window (shrunk towards 50% by a Beta(a, a) prior; reset at each window so no window
sees another window's outcomes). A day's outcome is known at the next open, before
the next decision. Non-conflict days keep eval-v1's decision. Two arbiters:
- vote: decide by sum_i d_i * (r_i - 0.5); NEUTRAL if its size is below m;
- reweight: multiply each Mediator contribution by r_i / 0.5, then the usual +-0.05 band.

    python scripts/reliability_arbiter.py select     # grid on the dev windows -> selected.json
    python scripts/reliability_arbiter.py evaluate   # the selected arbiter on test, once
    python scripts/reliability_arbiter.py longrun    # exploratory, see longrun()
    python scripts/reliability_arbiter.py conflicts  # simple resolution rules on conflict days
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from baselines.cryptotrade.env import DEV_WINDOWS, WINDOWS, load_prices  # noqa: E402
from scripts.trend_variants import AGENTS, check_reproduction, load_window, simulate  # noqa: E402

OUT = Path("outputs/reliability_arbiter")
BAND = 0.05
GRID = ([{"mode": "vote", "prior": a, "margin": m} for a in (2, 5, 10) for m in (0.0, 0.05)]
        + [{"mode": "reweight", "prior": a, "margin": 0.0} for a in (2, 5, 10)])


def run(window, mode, prior, margin):
    """-> actions, and (call, went_up) for the conflict days."""
    opens, rows = window["opens"], window["rows"]
    right = {a: 0 for a in AGENTS}
    seen = {a: 0 for a in AGENTS}
    actions, calls = [], []
    for k, row in enumerate(rows):
        dirs = {a: int(np.sign(c)) for a, c in row["contrib"].items()}
        conflict = row["ok"] and 1 in dirs.values() and -1 in dirs.values()
        if not conflict:
            actions.append(row["saved_action"])
            continue
        rel = {a: (right[a] + prior) / (seen[a] + 2 * prior) for a in AGENTS}
        if mode == "vote":
            score = sum(dirs[a] * (rel[a] - 0.5) for a in AGENTS)
            call = int(np.sign(score)) if abs(score) > margin else 0
        else:
            s = sum(row["contrib"][a] * rel[a] / 0.5 for a in AGENTS)
            call = 1 if s >= BAND else -1 if s <= -BAND else 0
        actions.append(0.5 * call)
        next_open = opens[rows[k + 1]["i"]] if k + 1 < len(rows) else window["last_open"]
        up = next_open > opens[row["i"]]
        calls.append((call, up))
        for a in AGENTS:  # the outcome is known at the next open, before the next decision
            if dirs[a]:
                seen[a] += 1
                right[a] += (dirs[a] > 0) == up
    return actions, calls


def score(windows, **cfg):
    per, allcalls = {}, []
    for w in windows:
        acts, calls = run(w, **cfg)
        per[w["name"]] = simulate(w, acts)
        allcalls += calls
    hits = [(c > 0) == up for c, up in allcalls if c]
    return {**cfg, "mean_return": float(np.mean([r["total_return"] for r in per.values()])),
            "mean_sharpe": float(np.mean([r["sharpe"] for r in per.values()])),
            "conflict_days": len(allcalls), "conflict_calls": len(hits),
            "conflict_accuracy": float(np.mean(hits)) if hits else None, "windows": per}


def baseline(windows):
    """eval-v1 on the same conflict days."""
    out = score(windows, mode="vote", prior=1, margin=0.0)  # only for its structure
    hits, n = [], 0
    for w in windows:
        opens, rows = w["opens"], w["rows"]
        for k, row in enumerate(rows):
            dirs = [int(np.sign(c)) for c in row["contrib"].values()]
            if row["ok"] and 1 in dirs and -1 in dirs:
                n += 1
                nxt = opens[rows[k + 1]["i"]] if k + 1 < len(rows) else w["last_open"]
                if row["saved_action"]:
                    hits.append((row["saved_action"] > 0) == (nxt > opens[row["i"]]))
    res = {w["name"]: simulate(w, [r["saved_action"] for r in w["rows"]]) for w in windows}
    out.update(mode="eval-v1", prior=None, margin=None, conflict_days=n, conflict_calls=len(hits),
               conflict_accuracy=float(np.mean(hits)), windows=res,
               mean_return=float(np.mean([r["total_return"] for r in res.values()])),
               mean_sharpe=float(np.mean([r["sharpe"] for r in res.values()])))
    return out


def label(r):
    if r["mode"] == "eval-v1":
        return "eval-v1 (debate)"
    return f"{r['mode']} prior={r['prior']}" + (f" margin={r['margin']}" if r["mode"] == "vote" else "")


def show(title, rows):
    print(title)
    for r in rows:
        per = "  ".join(f"{w}: {x['total_return'] * 100:+6.2f}%" for w, x in r["windows"].items())
        print(f"  {label(r):28s} conflict acc {r['conflict_accuracy'] * 100:5.1f}% ({r['conflict_calls']}/{r['conflict_days']})"
              f"  mean {r['mean_return'] * 100:+6.2f}%  sharpe {r['mean_sharpe']:+.3f} | {per}")


def longrun(prices, prior=5):
    """Exploratory: vote arbiter whose records carry across all six windows in time order.

    Closer to live use (the record keeps growing), but the dev windows' records then
    include outcomes of earlier test days and the idea came after the test conflict
    table had been seen, so this is not a held-out result.
    """
    windows = sorted([load_window(n, prices) for n in {**DEV_WINDOWS, **WINDOWS}], key=lambda w: w["rows"][0]["date"])
    right, seen = {a: 0 for a in AGENTS}, {a: 0 for a in AGENTS}
    out = {s: {"v1_hits": [], "arb_hits": [], "conflict_hits": [], "v1_conflict_hits": [], "returns": {}, "v1_returns": {}}
           for s in ("dev", "test")}
    for w in windows:
        s = "dev" if w["name"] in DEV_WINDOWS else "test"
        opens, rows, acts = w["opens"], w["rows"], []
        for k, row in enumerate(rows):
            nxt = opens[rows[k + 1]["i"]] if k + 1 < len(rows) else w["last_open"]
            up = nxt > opens[row["i"]]
            v1 = int(np.sign(row["saved_action"]))
            dirs = {a: int(np.sign(c)) for a, c in row["contrib"].items()}
            call = v1
            if row["ok"] and 1 in dirs.values() and -1 in dirs.values():
                rel = {a: (right[a] + prior) / (seen[a] + 2 * prior) for a in AGENTS}
                call = int(np.sign(sum(dirs[a] * (rel[a] - 0.5) for a in AGENTS)))
                if call:
                    out[s]["conflict_hits"].append((call > 0) == up)
                if v1:
                    out[s]["v1_conflict_hits"].append((v1 > 0) == up)
                for a in AGENTS:
                    if dirs[a]:
                        seen[a] += 1
                        right[a] += (dirs[a] > 0) == up
            acts.append(0.5 * call)
            for key, c in (("v1_hits", v1), ("arb_hits", call)):
                if c:
                    out[s][key].append((c > 0) == up)
        out[s]["returns"][w["name"]] = simulate(w, acts)["total_return"]
        out[s]["v1_returns"][w["name"]] = simulate(w, [r["saved_action"] for r in rows])["total_return"]
    summary = {"prior": prior, "final_record": {a: [int(right[a]), seen[a]] for a in AGENTS}}
    for s, r in out.items():
        summary[s] = {k: (float(np.mean(v)) if v else None) for k, v in r.items() if k.endswith("hits")}
        summary[s].update({f"{k}_n": len(v) for k, v in r.items() if k.endswith("hits")})
        summary[s]["mean_return"] = float(np.mean(list(r["returns"].values())))
        summary[s]["v1_mean_return"] = float(np.mean(list(r["v1_returns"].values())))
        summary[s]["returns"] = r["returns"]
    (OUT / "longrun.json").write_text(json.dumps(summary, indent=2))
    print(f"Exploratory long-run arbiter (prior {prior}); final record " +
          ", ".join(f"{a[:-6]} {r}/{n}" for a, (r, n) in summary["final_record"].items()))
    for s in ("dev", "test"):
        r = summary[s]
        print(f"  {s:4s} conflict days: acc {r['v1_conflict_hits'] * 100:.1f}% -> {r['conflict_hits'] * 100:.1f}%  | "
              f"all days: acc {r['v1_hits'] * 100:.1f}% ({r['v1_hits_n']}) -> {r['arb_hits'] * 100:.1f}% ({r['arb_hits_n']})  | "
              f"mean return {r['v1_mean_return'] * 100:+.2f}% -> {r['mean_return'] * 100:+.2f}%")


def conflicts(prices):
    """Direction accuracy of simple resolution rules on the days the specialists conflict.

    Here a conflict uses the specialists' own directions (170 days), not the Mediator's
    contributions used above (145 days): on 25 conflict days the Mediator gives one side a
    weight of zero.
    """
    import contextlib
    import copy
    import io
    from baselines.cryptotrade.ours import _midnight, run_mediator, signal_of
    from scripts.trend_variants import RUN_NAME, RUNS
    index = {d["date"]: i for i, d in enumerate(prices)}
    opens = np.array([d["open"] for d in prices])
    sign = {"BUY": 1, "SELL": -1, "NEUTRAL": 0}
    res = {}
    for name in [*DEV_WINDOWS, *WINDOWS]:
        s = "dev" if name in DEV_WINDOWS else "test"
        for path in sorted((RUNS / name / RUN_NAME / "days").glob("*.json")):
            day = json.loads(path.read_text())
            if day.get("status") != "ok":
                continue
            sp = {o["agent_id"]: o for o in day["specialists"]}
            dirs = {a: sp[a]["belief_vector"]["direction"] for a in AGENTS}
            if not (1 in dirs.values() and -1 in dirs.values()):
                continue
            i = index[day["date"]]
            up = opens[i + 1] > opens[i]
            with contextlib.redirect_stdout(io.StringIO()):
                no_debate = run_mediator([copy.deepcopy(sp[a]) for a in AGENTS], current_time=_midnight(day["date"]))
            calls = {"current system (debate)": sign[day["signal"]],
                     "Mediator without debate": sign[signal_of(no_debate["S_final"])],
                     "majority vote": int(np.sign(sum(dirs.values()))),
                     "most confident agent": dirs[max((a for a in AGENTS if dirs[a]), key=lambda a: sp[a]["confidence"])],
                     **{f"follow {a[:-6]}": dirs[a] for a in AGENTS}}
            for rule, c in calls.items():
                res.setdefault(rule, {"dev": [], "test": []})[s].append(None if c == 0 else bool((c > 0) == up))
    table = {}
    print("Conflict days:", {s: len(res["majority vote"][s]) for s in ("dev", "test")})
    for rule, by in res.items():
        row = {}
        for s in ("dev", "test", "pooled"):
            h = [x for x in (by["dev"] + by["test"] if s == "pooled" else by[s]) if x is not None]
            row[s] = {"accuracy": float(np.mean(h)), "calls": len(h)}
        table[rule] = row
        print(f"  {rule:26s} " + "  ".join(f"{s} {row[s]['accuracy'] * 100:5.1f}% ({row[s]['calls']})" for s in row))
    (OUT / "conflict_rules.json").write_text(json.dumps(table, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("step", choices=("select", "evaluate", "longrun", "conflicts"))
    args = parser.parse_args()
    prices = load_prices()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.step in ("longrun", "conflicts"):
        {"longrun": longrun, "conflicts": conflicts}[args.step](prices)
        return
    names = DEV_WINDOWS if args.step == "select" else WINDOWS
    windows = [load_window(n, prices) for n in names]
    check_reproduction(windows)
    if args.step == "select":
        rows = [score(windows, **c) for c in GRID]
        best = max(rows, key=lambda r: (round(r["mean_return"], 6), r["mean_sharpe"]))
        (OUT / "selected.json").write_text(json.dumps({"selected_on": list(DEV_WINDOWS), "selected": best,
                                                       "eval_v1": baseline(windows), "grid": rows}, indent=2))
        show("DEV (selection)", [baseline(windows), *rows])
        print(f"selected: {label(best)}")
        return
    sel = json.loads((OUT / "selected.json").read_text())["selected"]
    cfg = {k: sel[k] for k in ("mode", "prior", "margin")}
    result = {"evaluated_on": list(WINDOWS), "eval_v1": baseline(windows), "selected": score(windows, **cfg),
              "grid_after_selection": [score(windows, **c) for c in GRID]}
    (OUT / "test_result.json").write_text(json.dumps(result, indent=2))
    show("TEST (selected arbiter, evaluated once)", [result["eval_v1"], result["selected"]])
    show("TEST, whole grid (robustness only, not used for selection)", result["grid_after_selection"])


if __name__ == "__main__":
    main()
