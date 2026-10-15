"""Offline bias correction of the agents' signals (no LLM calls).

Each agent's score is direction * strength (BUY +, SELL -, NEUTRAL 0). The
Sentiment agent says BUY ~80% of the time and the Market agent ~40%, so a raw
score mostly repeats the agent's habit. Here every score is replaced by its
deviation from the agent's own mean over the previous K ok days of the window
("better or worse than usual"); the Mediator weight of the day is kept:
    contribution = weight * (score - mean of the previous K scores)
The first days of a window use the mean of whatever history exists (at least
MIN_HISTORY days), and no correction before that. Only past days are used.

    python scripts/bias_correction.py select    # choose K and the corrected agents on dev -> selected.json
    python scripts/bias_correction.py evaluate  # apply selected.json to the test windows, once
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from baselines.cryptotrade.env import DEV_WINDOWS, WINDOWS, load_prices  # noqa: E402
from baselines.cryptotrade.ours import ACTION, signal_of  # noqa: E402
from scripts.trend_variants import AGENTS, RUN_NAME, RUNS, load_window, simulate  # noqa: E402

OUT = Path("outputs/bias_correction")
MIN_HISTORY = 5
GRID = [dict(k=k, agents=agents) for k in (10, 20, 30)
        for agents in (AGENTS, ("Sentiment_Agent",), ("Market_Agent", "Sentiment_Agent"))]


def load(name, prices, run_name=RUN_NAME):
    """Window rows (for simulate) plus each ok day's per-agent score and weight."""
    window = load_window(name, prices)
    for row in window["rows"]:
        row["score"], row["weight"] = {}, {}
        if not row["ok"]:
            continue
        day = json.loads((RUNS / name / run_name / "days" / f"{row['date']}.json").read_text())
        for d in day["mediator"]["details"]:
            row["score"][d["agent_id"]] = d["direction"] * d["strength"]
            row["weight"][d["agent_id"]] = d["weight"]
    return window


def corrected_scores(window, k, agents):
    """Per row: {agent: score minus the agent's mean over the previous k ok days}."""
    history = {a: [] for a in AGENTS}
    out = []
    for row in window["rows"]:
        if not row["ok"]:
            out.append(None)
            continue
        scores = {}
        for a in AGENTS:
            past = history[a][-k:]
            base = np.mean(past) if a in agents and len(past) >= MIN_HISTORY else 0.0
            scores[a] = row["score"].get(a, 0.0) - base
            history[a].append(row["score"].get(a, 0.0))
        out.append(scores)
    return out


def actions(window, k=None, agents=()):
    scores = corrected_scores(window, k or 1, agents if k else ())
    acts = []
    for row, s in zip(window["rows"], scores):
        if s is None:
            acts.append(0.0)
            continue
        acts.append(ACTION[signal_of(sum(row["weight"].get(a, 0.0) * s[a] for a in AGENTS))])
    return acts


def accuracy(windows, k=None, agents=()):
    """Direction accuracy and BUY share of each agent's (corrected) score and of the final decision."""
    hits = {a: [] for a in (*AGENTS, "final")}
    buys = {a: [] for a in AGENTS}
    for w in windows:
        opens, rows = w["opens"], w["rows"]
        scores = corrected_scores(w, k or 1, agents if k else ())
        for j, (row, s, act) in enumerate(zip(rows, scores, actions(w, k, agents))):
            if s is None:
                continue
            nxt = opens[rows[j + 1]["i"]] if j + 1 < len(rows) else w["last_open"]
            up = nxt > opens[row["i"]]
            for a in AGENTS:
                if abs(s[a]) > 1e-9:
                    hits[a].append((s[a] > 0) == up)
                    buys[a].append(s[a] > 0)
            if act:
                hits["final"].append((act > 0) == up)
    return {a: {"accuracy": float(np.mean(h)) if h else None, "calls": len(h),
                **({"buy_share": float(np.mean(buys[a]))} if a in buys and buys[a] else {})}
            for a, h in hits.items()}


def score(windows, k=None, agents=()):
    results = {w["name"]: simulate(w, actions(w, k, agents)) for w in windows}
    return {"mean_return": float(np.mean([r["total_return"] for r in results.values()])),
            "mean_sharpe": float(np.mean([r["sharpe"] for r in results.values()])),
            "windows": results, "agents_accuracy": accuracy(windows, k, agents)}


def check_reproduction(windows):
    for w in windows:
        assert actions(w) == [r["saved_action"] for r in w["rows"]], f"saved actions differ in {w['name']}"


def print_row(name, s):
    per = "  ".join(f"{w}: {r['total_return'] * 100:+6.2f}%" for w, r in s["windows"].items())
    acc = s["agents_accuracy"]
    accs = " ".join(f"{a.split('_')[0][:4]} {acc[a]['accuracy'] * 100:4.1f}%/{acc[a].get('buy_share', 0) * 100:3.0f}%B"
                    for a in AGENTS)
    print(f"  {name:34s} mean {s['mean_return'] * 100:+6.2f}% sh {s['mean_sharpe']:+.3f} | {per}")
    print(f"  {'':34s} acc(agent/BUY share) {accs} | final {acc['final']['accuracy'] * 100:4.1f}% "
          f"({acc['final']['calls']})")


def select(prices):
    windows = [load(n, prices) for n in DEV_WINDOWS]
    check_reproduction(windows)
    print("DEV (selection)")
    base = score(windows)
    print_row("eval-v1 (no correction)", base)
    rows = []
    for g in GRID:
        s = {**g, **score(windows, g["k"], g["agents"])}
        rows.append(s)
        print_row(f"K={g['k']} {'+'.join(a.split('_')[0] for a in g['agents'])}", s)
    best = max(rows, key=lambda s: (s["mean_return"], s["mean_sharpe"]))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "selected.json").write_text(json.dumps(
        {"selected_on": list(DEV_WINDOWS), "baseline_eval_v1": base, "grid": rows, "selected": best}, indent=2))
    print(f"selected: K={best['k']} agents={best['agents']}")


def evaluate(prices):
    best = json.loads((OUT / "selected.json").read_text())["selected"]
    windows = [load(n, prices) for n in WINDOWS]
    check_reproduction(windows)
    result = {"evaluated_on": list(WINDOWS), "baseline_eval_v1": score(windows),
              "corrected": {"k": best["k"], "agents": best["agents"],
                            **score(windows, best["k"], tuple(best["agents"]))}}
    (OUT / "test_result.json").write_text(json.dumps(result, indent=2))
    print("TEST (selected config, evaluated once)")
    print_row("eval-v1 (no correction)", result["baseline_eval_v1"])
    print_row(f"K={best['k']} {'+'.join(a.split('_')[0] for a in best['agents'])}", result["corrected"])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("step", choices=("select", "evaluate"))
    {"select": select, "evaluate": evaluate}[parser.parse_args().step](load_prices())


if __name__ == "__main__":
    main()
