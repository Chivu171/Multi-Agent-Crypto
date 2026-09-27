"""Build the B2 evaluation tables from a finished evaluate_direction run.

python -m scripts.report_evaluation --run outputs/eval_v0_30d \
    --dataset data/datasets/pilot_2022_01_forecast_previous

Reads only saved results (never calls an LLM), so it can be rerun at any time.
Writes <run>/report/{per_day.csv, summary.json, REPORT.md}.
Configurations follow B1: always BUY, always SELL, no Debate, full system.
"""
import argparse
import csv
import json
from pathlib import Path

from utils.eval_metrics import (
    build_records,
    conflict_score_summary,
    debate_impact,
    is_correct,
    prediction_metrics,
    prices_from_records,
    s_final_buckets,
    simulate_trades,
)

FEES = (0.0, 0.001, 0.002)
BASE_FEE = 0.001
CONFIG_LABELS = {"always_buy": "Luôn BUY", "always_sell": "Luôn SELL",
                 "no_debate": "Không Debate", "full": "Đầy đủ (có Debate)"}
LIMITATIONS = [
    "Đánh giá sơ bộ trên 30 ngày tháng 1/2022: không phải tập kiểm tra độc lập "
    "(prompt/ngưỡng được phát triển trên chính giai đoạn này).",
    "Chỉ một giai đoạn thị trường (BTC giảm mạnh); baseline luôn SELL được lợi thế.",
    "Mẫu nhỏ: chênh lệch vài ngày đúng/sai chưa có ý nghĩa thống kê.",
    "Model có thể đã biết diễn biến giá 2022 từ dữ liệu huấn luyện.",
    "Mô phỏng lý tưởng: độ trễ bằng 0, bỏ trượt giá, funding và chi phí vay short.",
]


def config_records(records):
    """One record list per B1 configuration, all on the full calendar."""
    def base(r, ok, signal):
        return {"sample_id": r["sample_id"], "return_24h": r["return_24h"], "price": r["price"],
                "ok": ok, "signal": signal if ok else None}
    return {
        "always_buy": [base(r, True, "BUY") for r in records],
        "always_sell": [base(r, True, "SELL") for r in records],
        "no_debate": [base(r, r.get("signal_no_debate") is not None, r.get("signal_no_debate")) for r in records],
        "full": [base(r, r["ok"], r["signal"]) for r in records],
    }


def financial(records, prices, fee):
    sim = simulate_trades(records, prices, fee=fee)
    curve = sim["equity_curve"]
    daily = [{"sample_id": r["sample_id"], "equity_change": curve[i + 1] / curve[i] - 1}
             for i, r in enumerate(records) if curve[i] > 0]
    return {
        "cumulative_return": sim["cumulative_return"], "trade_count": sim["trade_count"],
        "trade_win_rate": sim["trade_win_rate"], "profit_factor": sim["profit_factor"],
        "profit_factor_note": sim["profit_factor_note"], "max_drawdown": sim["max_drawdown"],
        "ruined": sim["ruined"], "equity_curve": curve,
        "worst_days": sorted(daily, key=lambda d: d["equity_change"])[:3],
        "worst_trades": sorted(sim["trades"], key=lambda t: t["pnl_recorded"])[:3],
    }


def specialist_signals(run_dir, sample):
    path = run_dir / "days" / f"{sample}.json"
    day = json.loads(path.read_text()) if path.exists() else {}
    return {s["agent_id"]: (s["signal"], s["confidence"]) for s in day.get("specialists") or []}


def build_report(run_dir, dataset_dir):
    run_dir, dataset_dir = Path(run_dir), Path(dataset_dir)
    records = build_records(run_dir, dataset_dir)
    prices = prices_from_records(records)
    configs = config_records(records)
    per_day, opposed = [], []
    for r in records:
        agents = specialist_signals(run_dir, r["sample_id"])
        signals = {sig for sig, _ in agents.values()}
        if {"BUY", "SELL"} <= signals:
            opposed.append({"sample_id": r["sample_id"], "conflict_score": r.get("conflict_score"),
                            "debate_triggered": r.get("debate_triggered")})
        row = {"sample_id": r["sample_id"], "status": r["status"], "reason": r.get("reason") or ""}
        for name in ("Financial_Agent", "Market_Agent", "Sentiment_Agent"):
            sig, conf = agents.get(name, ("", ""))
            row[name.split("_")[0].lower()] = f"{sig} {conf}".strip()
        row.update({
            "signal_full": r["signal"] or "", "signal_no_debate": r.get("signal_no_debate") or "",
            "S_final": r.get("S_final", ""), "S_final_no_debate": r.get("S_final_no_debate", ""),
            "conflict_score": r.get("conflict_score", ""), "debate_triggered": r.get("debate_triggered", ""),
            "return_24h": r["return_24h"],
            "correct_full": "" if not r["ok"] else is_correct(r["signal"], r["return_24h"]),
            "correct_no_debate": "" if r.get("signal_no_debate") is None
            else is_correct(r["signal_no_debate"], r["return_24h"]),
        })
        per_day.append({k: ("" if v is None else v) for k, v in row.items()})
    status_counts = {}
    for r in records:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1
    summary = {
        "run": str(run_dir), "dataset": str(dataset_dir), "status_counts": status_counts,
        "prediction": {name: prediction_metrics(recs) for name, recs in configs.items()},
        "financial": {name: {str(fee): financial(recs, prices, fee) for fee in FEES}
                      for name, recs in configs.items()},
        "debate_impact": debate_impact(records),
        "conflict": conflict_score_summary(records),
        "s_final_buckets": s_final_buckets(records),
        "buy_vs_sell_days": opposed,
    }
    return per_day, summary


def pct(value):
    return "N/A" if value is None else f"{value * 100:.1f}%"


def render_markdown(summary):
    p, f = summary["prediction"], summary["financial"]
    lines = ["# Đánh giá v0 — 4 cấu hình trên cùng dữ liệu", "",
             f"Trạng thái các ngày: {json.dumps(summary['status_counts'], ensure_ascii=False)}", "",
             "## Chất lượng dự đoán", "",
             "| Cấu hình | Ngày hợp lệ | BUY/SELL | Đúng | Directional accuracy | Coverage | NEUTRAL |",
             "|---|---|---|---|---|---|---|"]
    for name, label in CONFIG_LABELS.items():
        m = p[name]
        lines.append(f"| {label} | {m['successful_days']}/{m['requested_days']} | {m['directional_predictions']} | "
                     f"{m['correct']} | {pct(m['directional_accuracy'])} | {pct(m['coverage'])} | {m['neutral_days']} |")
    lines += ["", "## Tài chính mô phỏng (vốn đầu 1.0)", "",
              "| Cấu hình | Phí/chiều | Lợi suất tích lũy | Số lệnh | Win rate | Profit factor | Max drawdown |",
              "|---|---|---|---|---|---|---|"]
    for name, label in CONFIG_LABELS.items():
        for fee in FEES:
            s = f[name][str(fee)]
            pf = s["profit_factor"]
            pf = f"{pf:.2f}" if pf is not None else (s["profit_factor_note"] or "N/A")
            lines.append(f"| {label} | {fee * 100:.1f}% | {pct(s['cumulative_return'])} | {s['trade_count']} | "
                         f"{pct(s['trade_win_rate'])} | {pf} | {pct(s['max_drawdown'])} |")
    lines += ["", f"### Ba ngày vốn giảm mạnh nhất (phí {BASE_FEE * 100:.1f}%)", ""]
    for name, label in CONFIG_LABELS.items():
        worst = ", ".join(f"{d['sample_id']} ({pct(d['equity_change'])})"
                          for d in f[name][str(BASE_FEE)]["worst_days"] if d["equity_change"] < 0)
        lines.append(f"- {label}: {worst or 'không có ngày lỗ'}")
    d = summary["debate_impact"]
    lines += ["", "## Tác động Debate", "",
              f"- Ngày có Debate hợp lệ: {d['debate_days']}; đổi tín hiệu: {d['signal_changed']} "
              f"(sai→đúng {d['wrong_to_right']}, đúng→sai {d['right_to_wrong']}, "
              f"BUY/SELL→NEUTRAL {d['call_to_neutral']}, NEUTRAL→BUY/SELL {d['neutral_to_call']}).",
              f"- Accuracy toàn lịch: không Debate {pct(d['accuracy_no_debate_all_days'])}, "
              f"có Debate {pct(d['accuracy_with_debate_all_days'])}; coverage "
              f"{pct(d['coverage_no_debate_all_days'])} → {pct(d['coverage_with_debate_all_days'])}.",
              "", "Ngày specialist có cả BUY và SELL:", ""]
    for day in summary["buy_vs_sell_days"]:
        lines.append(f"- {day['sample_id']}: conflict {day['conflict_score']}, "
                     f"Debate {'có' if day['debate_triggered'] else 'không'}")
    if not summary["buy_vs_sell_days"]:
        lines.append("- (không có)")
    lines += ["", "## Giới hạn", ""] + [f"- {item}" for item in LIMITATIONS]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, default=Path("data/datasets/pilot_2022_01_forecast_previous"))
    args = parser.parse_args()
    per_day, summary = build_report(args.run, args.dataset)
    out = args.run / "report"
    out.mkdir(exist_ok=True)
    with (out / "per_day.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(per_day[0]))
        writer.writeheader()
        writer.writerows(per_day)
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    (out / "REPORT.md").write_text(render_markdown(summary))
    print((out / "REPORT.md").read_text())


if __name__ == "__main__":
    main()
