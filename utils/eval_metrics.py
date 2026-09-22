"""Evaluation metrics for daily 24h BTC direction predictions.

Rules fixed in docs/Quy_tac_danh_gia_B1 (see chat log for the reviewed version):
- A "record" is one requested day: sample_id, ok (bool, pipeline completed),
  signal (BUY/SELL/NEUTRAL or None if not ok), return_24h (float, actual).
- Directional accuracy/coverage count only BUY/SELL days in the numerator;
  NEUTRAL counts as a successful run but not a directional call; failed days
  count in neither, and are reported separately (never merged with NEUTRAL).
- Trade simulation: BUY=long, SELL=short, NEUTRAL/failed=flat. A trade is a
  maximal run of consecutive days with the same BUY/SELL signal. Position
  size q = E / (P_open * (1+f)) at open, held constant until close. PnL is
  computed in money, not by compounding daily percentage returns (that would
  silently assume rebalancing every day, which is wrong for a held short).
"""
import datetime
import math
from typing import Any, Dict, List, Optional, Sequence

Record = Dict[str, Any]
VALID_SIGNALS = {"BUY", "SELL", "NEUTRAL"}


def validate_records(records: Sequence[Record]) -> None:
    """Kiểm tra đầu vào trước khi tính bất kỳ chỉ số nào: tín hiệu phải hợp
    lệ (khớp trạng thái ok), và nếu record có sample_id dạng ngày ISO thì
    chuỗi ngày phải liên tục, không trùng, không sai thứ tự."""
    if not records:
        raise ValueError("records rỗng — không có ngày nào để tính")

    for r in records:
        signal = r.get("signal")
        if r["ok"]:
            if signal not in VALID_SIGNALS:
                raise ValueError(
                    f"Tín hiệu không hợp lệ {signal!r} ở ngày ok=True "
                    f"(sample_id={r.get('sample_id')}); phải là một trong {VALID_SIGNALS}"
                )
        elif signal is not None:
            raise ValueError(
                f"Ngày lỗi (ok=False) phải có signal=None, gặp {signal!r} "
                f"(sample_id={r.get('sample_id')})"
            )

    sample_ids = [r.get("sample_id") for r in records]
    if all(s is not None for s in sample_ids):
        if len(set(sample_ids)) != len(sample_ids):
            raise ValueError(f"sample_id trùng lặp trong records: {sample_ids}")
        try:
            dates = [datetime.date.fromisoformat(str(s)[:10]) for s in sample_ids]
        except ValueError:
            dates = None
        if dates is not None:
            for prev, cur in zip(dates, dates[1:]):
                if (cur - prev).days != 1:
                    raise ValueError(
                        f"Chuỗi ngày không liên tục hoặc sai thứ tự: {prev.isoformat()} -> {cur.isoformat()} "
                        f"(cách nhau {(cur - prev).days} ngày, phải đúng 1 ngày)"
                    )


# ---------------------------------------------------------------------------
# Nhóm 1 — Chất lượng dự đoán (4 chỉ số: directional accuracy, BUY accuracy,
# SELL accuracy, coverage)
# ---------------------------------------------------------------------------

def is_correct(signal: Optional[str], return_24h: float) -> Optional[bool]:
    """True/False for a BUY/SELL call; None if the signal makes no directional claim."""
    if signal == "BUY":
        return return_24h > 0
    if signal == "SELL":
        return return_24h < 0
    return None


def _ratio(num: float, den: float) -> Optional[float]:
    return num / den if den else None


def prediction_metrics(records: Sequence[Record]) -> Dict[str, Any]:
    validate_records(records)
    successful = [r for r in records if r["ok"]]
    directional = [r for r in successful if r["signal"] in ("BUY", "SELL")]
    correct = sum(is_correct(r["signal"], r["return_24h"]) for r in directional)
    out: Dict[str, Any] = {
        "requested_days": len(records),
        "successful_days": len(successful),
        "failed_days": len(records) - len(successful),
        "neutral_days": sum(r["signal"] == "NEUTRAL" for r in successful),
        "directional_predictions": len(directional),
        "correct": correct,
        "directional_accuracy": _ratio(correct, len(directional)),
        "coverage": _ratio(len(directional), len(records)),
        "success_rate": _ratio(len(successful), len(records)),
    }
    for side in ("BUY", "SELL"):
        group = [r for r in directional if r["signal"] == side]
        hits = sum(is_correct(side, r["return_24h"]) for r in group)
        out[f"{side.lower()}_accuracy"] = {"count": len(group), "correct": hits, "accuracy": _ratio(hits, len(group))}
    return out


# ---------------------------------------------------------------------------
# Nhóm 2 — Hiệu quả tài chính (4 chỉ số: cumulative return, trade win rate,
# profit factor, maximum drawdown), qua một bộ mô phỏng giao dịch theo ngày.
# ---------------------------------------------------------------------------

def _position(signal: Optional[str], ok: bool, allow_short: bool) -> int:
    if not ok:
        return 0
    if signal == "BUY":
        return 1
    if signal == "SELL":
        return -1 if allow_short else 0
    return 0


def _pnl(side: int, p_open: float, p_close: float, q: float, fee: float, *, exit_fee: bool) -> float:
    """PnL in money. side=+1 long, -1 short. exit_fee=False -> unrealized mark
    (entry fee already sunk, exit fee not yet charged)."""
    gross = q * (p_close - p_open) if side == 1 else q * (p_open - p_close)
    cost = fee * q * p_open + (fee * q * p_close if exit_fee else 0.0)
    return gross - cost


def simulate_trades(records: Sequence[Record], prices: Sequence[float],
                     fee: float = 0.001, allow_short: bool = True,
                     initial_equity: float = 1.0) -> Dict[str, Any]:
    """records[i] is day i (signal, ok); prices has len(records)+1 entries:
    prices[i] is the reference price at the start of day i (== end of day i-1),
    prices[n] is the price 24h after the last requested day."""
    validate_records(records)
    n = len(records)
    assert len(prices) == n + 1, "prices must bracket every requested day (n+1 points)"

    equity = initial_equity
    position = 0        # +1 long, -1 short, 0 flat
    entry_price = entry_equity = q = None
    ruined = False
    trades: List[Dict[str, Any]] = []
    curve = [equity]

    def close(side: int, p_open: float, p_close: float, qty: float, e_open: float, *, forced_final: bool) -> None:
        nonlocal equity, ruined
        pnl_formula = _pnl(side, p_open, p_close, qty, fee, exit_fee=True)
        new_equity = e_open + pnl_formula
        if new_equity <= 0:
            pnl_recorded = -e_open
            ruin_excess = pnl_formula - pnl_recorded  # negative: loss beyond what the capped equity shows
            equity = 0.0
            ruined = True
        else:
            pnl_recorded = pnl_formula
            ruin_excess = 0.0
            equity = new_equity
        trades.append({
            "side": "long" if side == 1 else "short", "entry_price": p_open, "exit_price": p_close,
            "pnl_formula": pnl_formula, "pnl_recorded": pnl_recorded, "ruin_excess_loss": ruin_excess,
            "ruined": ruined and not forced_final or (ruined and forced_final),
        })

    for k in range(n):
        if ruined:
            curve.append(0.0)
            continue
        p_k, p_k1 = prices[k], prices[k + 1]
        rec = records[k]
        target_pos = _position(rec.get("signal"), rec["ok"], allow_short)
        is_last = k == n - 1

        if target_pos != position:
            if position != 0:
                close(position, entry_price, p_k, q, entry_equity, forced_final=False)
                position = 0
            if not ruined and target_pos != 0:
                entry_price, entry_equity = p_k, equity
                q = entry_equity / (entry_price * (1 + fee))
                position = target_pos

        if ruined:
            curve.append(0.0)
            continue
        if position == 0:
            curve.append(equity)
        elif is_last:
            close(position, entry_price, p_k1, q, entry_equity, forced_final=True)
            position = 0
            curve.append(equity)
        else:
            mark = entry_equity + _pnl(position, entry_price, p_k1, q, fee, exit_fee=False)
            if mark <= 0:
                close(position, entry_price, p_k1, q, entry_equity, forced_final=False)
                position = 0
                curve.append(equity)
            else:
                curve.append(mark)

    # Lệnh hòa vốn (pnl_recorded == 0) không phải lệnh thắng cũng không phải
    # lệnh thua — không được đếm vào losing_trades (trước đây dùng <= 0, sai).
    wins = [t for t in trades if t["pnl_recorded"] > 0]
    losses = [t for t in trades if t["pnl_recorded"] < 0]
    breakeven = [t for t in trades if t["pnl_recorded"] == 0]
    loss_sum = -sum(t["pnl_recorded"] for t in losses)
    win_sum = sum(t["pnl_recorded"] for t in wins)
    if not trades:
        profit_factor, profit_factor_note = None, "no_trades"
    elif not losses and not wins:
        profit_factor, profit_factor_note = None, "no_wins_or_losses"  # toàn lệnh hòa vốn
    elif not losses:
        profit_factor, profit_factor_note = None, "no_losing_trades"
    elif not wins:
        profit_factor, profit_factor_note = 0.0, None
    else:
        profit_factor, profit_factor_note = win_sum / loss_sum, None

    return {
        "fee": fee, "allow_short": allow_short, "ruined": ruined,
        "equity_curve": curve, "trades": trades,
        "cumulative_return": curve[-1] / initial_equity - 1,
        "trade_count": len(trades),
        "trade_win_rate": _ratio(len(wins), len(trades)),
        "profit_factor": profit_factor,
        "profit_factor_note": profit_factor_note,
        "profit_factor_winning_trades": len(wins),
        "profit_factor_losing_trades": len(losses),
        "profit_factor_breakeven_trades": len(breakeven),
        "max_drawdown": max_drawdown(curve),
    }


def max_drawdown(curve: Sequence[float]) -> float:
    peak, worst = curve[0], 0.0
    for v in curve:
        peak = max(peak, v)
        if peak > 0:
            worst = max(worst, (peak - v) / peak)
        elif v < peak:
            worst = max(worst, 1.0)
    return worst


def prices_from_records(records: Sequence[Record]) -> List[float]:
    """Build the n+1 boundary-price series from each day's own reference_price
    and return_24h — does not assume the next day's reference_price matches."""
    prices = [r["price"] for r in records]
    last = records[-1]
    prices.append(last["price"] * (1 + last["return_24h"]))
    return prices


# ---------------------------------------------------------------------------
# Nhóm 3, đợt a — đọc trực tiếp từ output đã có (S_final theo khoảng, conflict
# score, tỷ lệ chạy thành công). Không cần tính lại gì.
# ---------------------------------------------------------------------------

def success_rate(records: Sequence[Record]) -> Optional[float]:
    return _ratio(sum(r["ok"] for r in records), len(records))


def s_final_buckets(records: Sequence[Record], edges: Sequence[float] = (0.05, 0.15, 0.30)) -> List[Dict[str, Any]]:
    bounds = list(edges) + [math.inf]
    rows = []
    for side in ("BUY", "SELL"):
        for lo, hi in zip(bounds[:-1], bounds[1:]):
            group = [r for r in records if r["ok"] and r["signal"] == side and lo <= abs(r["S_final"]) < hi]
            hits = sum(is_correct(side, r["return_24h"]) for r in group)
            label = f"[{lo},{hi})" if hi != math.inf else f"[{lo},inf)"
            rows.append({"signal": side, "abs_S_final": label, "count": len(group), "correct": hits,
                        "accuracy": _ratio(hits, len(group))})
    return rows


def conflict_score_summary(records: Sequence[Record], threshold: float = 0.4) -> Dict[str, Any]:
    scored = [r for r in records if r["ok"] and r.get("conflict_score") is not None]
    triggered = [r for r in scored if r["conflict_score"] >= threshold]
    return {
        "scored_days": len(scored),
        "mean_conflict_score": _ratio(sum(r["conflict_score"] for r in scored), len(scored)),
        "debate_triggered_days": len(triggered),
        "debate_trigger_rate": _ratio(len(triggered), len(scored)),
    }


# ---------------------------------------------------------------------------
# Nhóm 3, đợt b — cần tính lại tín hiệu "nếu không có Debate" bằng cách gọi
# lại Mediator trên đầu ra specialist gốc (day["specialists"] luôn là bản
# trước Debate — xem scripts/evaluate_direction.py: result["specialists"] =
# outputs được lưu trước khi Validator/Debate chạy).
# ---------------------------------------------------------------------------

def classify_signal(s_final: float, band: float) -> str:
    if s_final > band:
        return "BUY"
    if s_final < -band:
        return "SELL"
    return "NEUTRAL"


def build_records(run_dir, dataset_dir) -> List[Record]:
    """Ghép một thư mục kết quả chạy (run_dir, dạng outputs/direction_pilot*)
    với dataset (reference_price/return_24h từ labels.csv), tính lại S_final
    không-Debate cho từng ngày chạy thành công. Đọc labels.csv sau cùng."""
    import csv
    import datetime as dt
    import hashlib
    import json as _json
    from pathlib import Path

    from agents.mediator_agent import run_mediator
    from utils.thresholds import SIGNAL_NEUTRAL_BAND

    run_dir, dataset_dir = Path(run_dir), Path(dataset_dir)
    manifest = _json.loads((dataset_dir / "dataset_manifest.json").read_text())
    snapshot_lines = (dataset_dir / "snapshots.jsonl").read_text().splitlines()

    label_bytes = (dataset_dir / "labels.csv").read_bytes()
    if hashlib.sha256(label_bytes).hexdigest() != manifest["artifacts_sha256"]["labels.csv"]:
        raise ValueError("labels.csv không khớp checksum trong dataset_manifest.json")
    labels = {row["sample_id"]: row for row in csv.DictReader(label_bytes.decode().splitlines())}

    records: List[Record] = []
    for line in snapshot_lines:
        snap = _json.loads(line)
        sample = snap["sample_id"]
        label = labels[sample]
        rec: Record = {
            "sample_id": sample, "ok": False, "signal": None,
            "return_24h": float(label["return_24h"]), "price": float(label["reference_price"]),
        }
        day_path = run_dir / "days" / f"{sample}.json"
        day = _json.loads(day_path.read_text()) if day_path.exists() else {}
        if day.get("status") == "ok":
            ref = dt.datetime.fromisoformat(snap["prediction_time"])
            s_no_debate = run_mediator(day["specialists"], current_time=ref)["S_final"]
            rec.update({
                "ok": True, "signal": day["signal"], "S_final": day["S_final"],
                "conflict_score": day["validation"]["conflict_score"],
                "debate_triggered": bool(day["validation"]["conflict_detected"]),
                "S_final_no_debate": s_no_debate,
                "signal_no_debate": classify_signal(s_no_debate, SIGNAL_NEUTRAL_BAND),
            })
        records.append(rec)
    return records


def debate_impact(records: Sequence[Record]) -> Dict[str, Any]:
    """Nhóm 3b: tỷ lệ đổi tín hiệu do Debate; chất lượng dự đoán trước/sau đo
    ở hai phạm vi riêng — (a) chỉ trên các ngày có Debate hợp lệ, để thấy tác
    động trực tiếp của Debate; (b) trên toàn bộ ngày yêu cầu, để so sánh đúng
    quy tắc baseline "multi-agent không Debate" và "hệ thống đầy đủ" đã chốt."""
    debate_days = [r for r in records if r["ok"] and r.get("debate_triggered")]
    changed = [r for r in debate_days if r["signal"] != r["signal_no_debate"]]

    if debate_days:
        before = [{"ok": True, "signal": r["signal_no_debate"], "return_24h": r["return_24h"]} for r in debate_days]
        after = [{"ok": True, "signal": r["signal"], "return_24h": r["return_24h"]} for r in debate_days]
        before_m, after_m = prediction_metrics(before), prediction_metrics(after)
        accuracy_before, accuracy_after = before_m["directional_accuracy"], after_m["directional_accuracy"]
        coverage_before, coverage_after = before_m["coverage"], after_m["coverage"]
    else:
        accuracy_before = accuracy_after = coverage_before = coverage_after = None

    # (b) toàn bộ ngày yêu cầu — giữ nguyên trạng thái ok của từng ngày để
    # coverage/accuracy chia đúng cho tổng số ngày yêu cầu, không chỉ số ngày
    # có Debate. Ngày ok nhưng chưa tính lại được signal_no_debate (ví dụ
    # records dựng tay, chưa gọi build_records) bị coi như ngày lỗi ở nhánh
    # "không Debate" vì không có gì để so sánh.
    full_before, full_after = [], []
    for r in records:
        has_no_debate = r["ok"] and r.get("signal_no_debate") is not None
        full_before.append({"ok": has_no_debate, "signal": r.get("signal_no_debate") if has_no_debate else None,
                            "return_24h": r["return_24h"]})
        full_after.append({"ok": r["ok"], "signal": r.get("signal"), "return_24h": r["return_24h"]})
    full_before_m, full_after_m = prediction_metrics(full_before), prediction_metrics(full_after)

    wrong_to_right = right_to_wrong = call_to_neutral = neutral_to_call = other_changes = 0
    for r in changed:
        b, a = is_correct(r["signal_no_debate"], r["return_24h"]), is_correct(r["signal"], r["return_24h"])
        if b is False and a is True:
            wrong_to_right += 1
        elif b is True and a is False:
            right_to_wrong += 1
        elif b is not None and a is None:
            call_to_neutral += 1
        elif b is None and a is not None:
            neutral_to_call += 1
        else:
            other_changes += 1

    return {
        "debate_days": len(debate_days),
        "signal_changed": len(changed),
        "signal_change_rate": _ratio(len(changed), len(debate_days)),
        # (a) chỉ trên các ngày có Debate — đo tác động trực tiếp
        "accuracy_before_debate": accuracy_before,
        "accuracy_after_debate": accuracy_after,
        "coverage_before_debate": coverage_before,
        "coverage_after_debate": coverage_after,
        # (b) toàn bộ ngày yêu cầu — đúng phạm vi baseline đã chốt trong B1
        "accuracy_no_debate_all_days": full_before_m["directional_accuracy"],
        "accuracy_with_debate_all_days": full_after_m["directional_accuracy"],
        "coverage_no_debate_all_days": full_before_m["coverage"],
        "coverage_with_debate_all_days": full_after_m["coverage"],
        "wrong_to_right": wrong_to_right,
        "right_to_wrong": right_to_wrong,
        "call_to_neutral": call_to_neutral,
        "neutral_to_call": neutral_to_call,
        "other_changes": other_changes,
        "net_correct_change": wrong_to_right - right_to_wrong,
    }
