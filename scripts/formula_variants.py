"""Recompute a finished run's final signals under alternative Mediator weights.

python -m scripts.formula_variants --run outputs/eval_v0_30d

Offline ablation for the advisor meeting: each variant changes one weighting
component and reruns the Mediator on the saved final agent outputs. No LLM
calls; the conflict score (and so whether Debate ran) does not use entropy.
"""
import argparse
import copy
import csv
import datetime as dt
import json
from pathlib import Path
from unittest.mock import patch

from agents.mediator_agent import run_mediator
from utils import penalties
from utils.eval_metrics import (
    classify_signal,
    prediction_metrics,
    prices_from_records,
    simulate_trades,
)
from utils.thresholds import SIGNAL_NEUTRAL_BAND

ONCHAIN = ("hash-rate", "miners-revenue", "n-transactions", "estimated-transaction-volume-usd")


def financial_entropy(metrics, keys):
    # Same formula as agents/financial_agent.py, on a chosen subset of metrics.
    changes = [abs(metrics[k]["pct_change_1d"]) for k in keys]
    return min(max(sum(changes) / len(changes) / 30.0, 0.0), 1.0)


def drop_tx_volume(outputs, day):
    metrics = day["inputs"]["financial"]["metrics"]
    for out in outputs:
        if out["agent_id"] == "Financial_Agent":
            out["metadata"]["entropy"] = financial_entropy(metrics, ONCHAIN[:3])


def cap_entropy(outputs, day):
    for out in outputs:
        out["metadata"]["entropy"] = min(out["metadata"]["entropy"], 0.8)


def no_entropy(outputs, day):
    for out in outputs:
        out["metadata"]["entropy"] = 0.0


VARIANTS = {
    "v0": ("Hệ thống hiện tại", None, False),
    "drop_tx_volume": ("Bỏ khối lượng giao dịch USD khỏi entropy Financial", drop_tx_volume, False),
    "entropy_floor": ("Phạt entropy tối đa 80% (trọng số ≥ 20%)", cap_entropy, False),
    "no_entropy": ("Không phạt entropy", no_entropy, False),
    "no_time_decay": ("Không phạt thời gian", None, True),
}


def final_signal(day, adjust, no_decay):
    outputs = copy.deepcopy((day.get("validation") or {}).get("debate_updated_outputs") or day["specialists"])
    if adjust:
        adjust(outputs, day)
    ref = dt.datetime.fromisoformat(day["sample_id"] + "T00:00:00+00:00")
    if no_decay:
        with patch.object(penalties, "time_decay_penalty", lambda *args, **kwargs: 1.0):
            s_final = run_mediator(outputs, current_time=ref)["S_final"]
    else:
        s_final = run_mediator(outputs, current_time=ref)["S_final"]
    return classify_signal(s_final, SIGNAL_NEUTRAL_BAND), s_final


def evaluate(run_dir, dataset_dir, fee=0.001):
    labels = {r["sample_id"]: r for r in csv.DictReader((dataset_dir / "labels.csv").read_text().splitlines())}
    days = {}
    for sample in labels:
        path = run_dir / "days" / f"{sample}.json"
        days[sample] = json.loads(path.read_text()) if path.exists() else {}
    results, per_day = {}, {s: {"return_24h": float(labels[s]["return_24h"])} for s in labels}
    for name, (label, adjust, no_decay) in VARIANTS.items():
        records = []
        for sample, day in days.items():
            record = {"sample_id": sample, "ok": day.get("status") == "ok", "signal": None,
                      "return_24h": float(labels[sample]["return_24h"]),
                      "price": float(labels[sample]["reference_price"])}
            if record["ok"]:
                record["signal"], s_final = final_signal(day, adjust, no_decay)
                per_day[sample][name] = record["signal"]
            records.append(record)
        m = prediction_metrics(records)
        sim = simulate_trades(records, prices_from_records(records), fee=fee)
        results[name] = {"label": label, "buy_days": m["buy_accuracy"]["count"],
                         "sell_days": m["sell_accuracy"]["count"], "neutral_days": m["neutral_days"],
                         "correct": m["correct"], "directional": m["directional_predictions"],
                         "accuracy": m["directional_accuracy"], "coverage": m["coverage"],
                         "cumulative_return": sim["cumulative_return"], "max_drawdown": sim["max_drawdown"]}
    return results, per_day


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, default=Path("data/datasets/pilot_2022_01_forecast_previous"))
    args = parser.parse_args()
    results, per_day = evaluate(args.run, args.dataset)
    out = args.run / "report" / "formula_variants.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"variants": results, "per_day": per_day}, indent=2, ensure_ascii=False) + "\n")
    pct = lambda v: "N/A" if v is None else f"{v * 100:.1f}%"
    print("| Phương án | BUY | SELL | NEUTRAL | Đúng/BUY+SELL | Accuracy | Coverage | Lợi suất (phí 0,1%) | MDD |")
    print("|---|---|---|---|---|---|---|---|---|")
    for r in results.values():
        print(f"| {r['label']} | {r['buy_days']} | {r['sell_days']} | {r['neutral_days']} | "
              f"{r['correct']}/{r['directional']} | {pct(r['accuracy'])} | {pct(r['coverage'])} | "
              f"{pct(r['cumulative_return'])} | {pct(r['max_drawdown'])} |")


if __name__ == "__main__":
    main()
