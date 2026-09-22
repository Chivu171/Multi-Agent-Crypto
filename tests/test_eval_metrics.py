"""21 test case tính tay từ Quy_tac_danh_gia_B1 (mục 4.1), cộng vài ca đối chứng
với outputs/direction_pilot_retry (bước 1). Không gọi LLM."""
import json
import math
from pathlib import Path

import pytest

from utils.eval_metrics import (
    build_records,
    classify_signal,
    conflict_score_summary,
    debate_impact,
    is_correct,
    max_drawdown,
    prediction_metrics,
    prices_from_records,
    s_final_buckets,
    simulate_trades,
    success_rate,
)


def day(signal, return_24h, ok=True, price=None, **extra):
    r = {"signal": signal, "return_24h": return_24h, "ok": ok}
    if price is not None:
        r["price"] = price
    r.update(extra)
    return r


# ---- 4.1: kiểm tra phép tính ----------------------------------------------

def test_case_1_buy_correct():
    assert is_correct("BUY", 0.02) is True


def test_case_2_buy_wrong():
    assert is_correct("BUY", -0.03) is False


def test_case_3_sell_correct():
    assert is_correct("SELL", -0.02) is True


def test_case_4_sell_wrong():
    assert is_correct("SELL", 0.04) is False


def test_case_5_no_change_is_wrong_and_counted():
    assert is_correct("BUY", 0.0) is False
    assert is_correct("SELL", 0.0) is False
    recs = [day("BUY", 0.0)]
    m = simulate_trades(recs, prices=[100, 100], fee=0.0)
    assert m["trade_count"] == 1
    assert m["trades"][0]["pnl_recorded"] == pytest.approx(0.0)
    assert m["trade_win_rate"] == 0.0  # breakeven trade is not a win, but is in the sample


def test_case_6_neutral_day():
    recs = [day("NEUTRAL", 0.01)]
    m = prediction_metrics(recs)
    assert m["directional_predictions"] == 0
    assert m["coverage"] == 0.0
    assert m["success_rate"] == 1.0
    sim = simulate_trades(recs, prices=[100, 101], fee=0.0)
    assert sim["trade_count"] == 0


def test_case_7_error_day_after_buy():
    recs = [day("BUY", 0.02, ok=True, price=100), day(None, 0.0, ok=False, price=102)]
    m = prediction_metrics(recs)
    assert m["requested_days"] == 2
    assert m["coverage"] == 0.5          # error day not in numerator
    assert m["success_rate"] == 0.5      # error day not counted as successful
    sim = simulate_trades(recs, prices=[100, 102, 999], fee=0.0)
    assert sim["trade_count"] == 1
    assert sim["trades"][0]["exit_price"] == 102
    assert sim["trades"][0]["pnl_recorded"] == pytest.approx(0.02)  # +2% of E=1


def test_case_8_all_neutral():
    recs = [day("NEUTRAL", 0.0) for _ in range(5)]
    m = prediction_metrics(recs)
    assert m["directional_accuracy"] is None
    assert m["coverage"] == 0.0
    assert m["success_rate"] == 1.0
    sim = simulate_trades(recs, prices=[100] * 6, fee=0.0)
    assert sim["trade_count"] == 0
    assert sim["cumulative_return"] == 0.0
    assert sim["trade_win_rate"] is None
    assert sim["profit_factor"] is None


def test_case_9_two_losing_trades():
    recs = [day("BUY", -0.03, price=100), day("SELL", -0.02, price=103)]
    # BUY closes at 103 (loss), SELL then opens; force SELL to close losing too
    recs2 = [day("BUY", 0, price=100), day("SELL", 0, price=100)]
    sim = simulate_trades(recs2, prices=[100, 97, 99], fee=0.0)
    assert sim["trade_count"] == 2
    assert all(t["pnl_recorded"] < 0 for t in sim["trades"])
    assert sim["trade_win_rate"] == 0.0
    assert sim["profit_factor"] == 0.0


def test_case_10_two_winning_trades_no_losses():
    recs = [day("BUY", 0, price=100), day("SELL", 0, price=103)]
    sim = simulate_trades(recs, prices=[100, 103, 101], fee=0.0)
    assert sim["trade_count"] == 2
    assert all(t["pnl_recorded"] > 0 for t in sim["trades"])
    assert sim["trade_win_rate"] == 1.0
    assert sim["profit_factor"] == "no_losing_trades"
    assert sim["profit_factor_losing_trades"] == 0


def test_case_11_short_hold_multiple_days_no_daily_compounding():
    recs = [day("SELL", 0, price=100), day("SELL", 0, price=90)]
    sim = simulate_trades(recs, prices=[100, 90, 95], fee=0.0)
    assert sim["trade_count"] == 1
    assert sim["trades"][0]["pnl_recorded"] == pytest.approx(0.05)  # 1 - 95/100
    wrong_daily_compound = (1 + 0.10) * (1 - 95 / 90) - 1
    assert sim["trades"][0]["pnl_recorded"] != pytest.approx(wrong_daily_compound)


def test_case_12_buy_hold_three_days_single_fee():
    recs = [day("BUY", 0, price=100)] * 3
    sim = simulate_trades(recs, prices=[100, 100, 100, 102], fee=0.001)
    assert sim["trade_count"] == 1
    q = 1 / (100 * 1.001)
    expected = q * 2 - 0.001 * q * (100 + 102)
    assert sim["trades"][0]["pnl_recorded"] == pytest.approx(expected)


def test_case_13_reversal_no_fee():
    recs = [day("BUY", 0, price=100), day("SELL", 0, price=110)]
    sim = simulate_trades(recs, prices=[100, 110, 99], fee=0.0)
    assert sim["trade_count"] == 2
    assert sim["equity_curve"][-1] == pytest.approx(1.10 * 1.10)


def test_case_14_fee_on_long():
    recs = [day("BUY", 0, price=100)]
    sim = simulate_trades(recs, prices=[100, 110], fee=0.001)
    assert sim["cumulative_return"] == pytest.approx(0.0978022, abs=1e-6)


def test_case_15_max_drawdown_from_curve():
    curve = [1.00, 1.10, 0.88, 0.99]
    assert max_drawdown(curve) == pytest.approx(0.2)


def test_case_16_profit_factor_uses_money_not_percent():
    equity = 1.0
    pnls = []
    for r in (0.10, -0.04, 0.06, -0.06):
        pnl = equity * r
        pnls.append(pnl)
        equity += pnl
    wins = sum(p for p in pnls if p > 0)
    losses = -sum(p for p in pnls if p <= 0)
    pf = wins / losses
    assert pf == pytest.approx(1.46957, abs=1e-4)
    assert pf != pytest.approx(16 / 10)


def test_case_17_no_price_change_with_fee_is_a_loss():
    recs = [day("BUY", 0, price=100)]
    sim = simulate_trades(recs, prices=[100, 100], fee=0.001)
    assert sim["trades"][0]["pnl_recorded"] < 0
    assert sim["trade_win_rate"] == 0.0


def test_case_18_reversal_with_fees():
    recs = [day("BUY", 0, price=100), day("SELL", 0, price=110)]
    sim = simulate_trades(recs, prices=[100, 110, 99], fee=0.001)
    assert sim["cumulative_return"] == pytest.approx(0.205389, abs=1e-5)


def test_case_19_all_error_days():
    recs = [day(None, 0.0, ok=False) for _ in range(3)]
    m = prediction_metrics(recs)
    assert m["success_rate"] == 0.0
    assert m["coverage"] == 0.0
    assert m["directional_accuracy"] is None
    sim = simulate_trades(recs, prices=[100, 100, 100, 100], fee=0.0)
    assert sim["trade_count"] == 0
    assert sim["cumulative_return"] == 0.0


def test_case_20_all_breakeven_trades():
    recs = [day("BUY", 0, price=100), day("SELL", 0, price=100)]
    sim = simulate_trades(recs, prices=[100, 100, 100], fee=0.0)
    assert sim["trade_count"] == 2
    assert sim["trade_win_rate"] == 0.0
    assert sim["profit_factor"] is None  # no losses either


def test_case_21_ruin_caps_equity_at_zero():
    recs = [day("SELL", 0, price=100)]
    sim = simulate_trades(recs, prices=[100, 250], fee=0.0)
    assert sim["ruined"] is True
    assert sim["cumulative_return"] == pytest.approx(-1.0)
    assert sim["max_drawdown"] == pytest.approx(1.0)
    t = sim["trades"][0]
    assert t["pnl_formula"] == pytest.approx(-1.5)
    assert t["pnl_recorded"] == pytest.approx(-1.0)
    assert t["ruin_excess_loss"] == pytest.approx(-0.5)


# ---- Nhóm 3, đợt a: chưa có test tay — bổ sung ----------------------------

def test_success_rate_standalone():
    recs = [day("BUY", 0.01), day(None, 0.0, ok=False), day("NEUTRAL", 0.0)]
    assert success_rate(recs) == pytest.approx(2 / 3)
    assert success_rate([]) is None


def test_s_final_buckets_splits_by_side_and_magnitude():
    recs = [
        day("BUY", 0.01, S_final=0.10),   # |S_final| in [0.05,0.15), đúng
        day("BUY", -0.01, S_final=0.12),  # cùng khoảng, sai
        day("BUY", 0.01, S_final=0.20),   # khoảng [0.15,0.30), đúng
        day("SELL", -0.01, S_final=-0.40),  # SELL, khoảng [0.30,inf), đúng
        day(None, 0.0, ok=False, S_final=0.10),  # ngày lỗi: phải bị loại
    ]
    rows = {(r["signal"], r["abs_S_final"]): r for r in s_final_buckets(recs)}
    buy_low = rows[("BUY", "[0.05,0.15)")]
    assert buy_low["count"] == 2 and buy_low["correct"] == 1 and buy_low["accuracy"] == pytest.approx(0.5)
    buy_mid = rows[("BUY", "[0.15,0.3)")]
    assert buy_mid["count"] == 1 and buy_mid["correct"] == 1
    sell_high = rows[("SELL", "[0.3,inf)")]
    assert sell_high["count"] == 1 and sell_high["correct"] == 1
    buy_high = rows[("BUY", "[0.3,inf)")]
    assert buy_high["count"] == 0 and buy_high["accuracy"] is None


def test_conflict_score_summary_counts_trigger_days():
    recs = [
        day("BUY", 0.01, conflict_score=0.10),
        day("SELL", -0.01, conflict_score=0.50),  # >= 0.4 -> triggered
        day("BUY", 0.01, conflict_score=0.40),    # == 0.4 -> triggered (biên)
        day(None, 0.0, ok=False, conflict_score=0.90),  # ngày lỗi: bị loại
    ]
    s = conflict_score_summary(recs, threshold=0.4)
    assert s["scored_days"] == 3
    assert s["debate_triggered_days"] == 2
    assert s["debate_trigger_rate"] == pytest.approx(2 / 3)
    assert s["mean_conflict_score"] == pytest.approx((0.10 + 0.50 + 0.40) / 3)


def test_classify_signal_thresholds():
    assert classify_signal(0.06, 0.05) == "BUY"
    assert classify_signal(-0.06, 0.05) == "SELL"
    assert classify_signal(0.05, 0.05) == "NEUTRAL"   # đúng biên: không > band
    assert classify_signal(0.0, 0.05) == "NEUTRAL"


# ---- Nhóm 3, đợt b: debate_impact trên dữ liệu tay -------------------------

def test_debate_impact_hand_case():
    # 4 ngày có Debate hợp lệ: 1 sai->đúng, 1 đúng->sai, 1 không đổi, 1 NEUTRAL->call
    recs = [
        day("BUY", 0.01, debate_triggered=True, signal_no_debate="SELL"),   # sai -> đúng
        day("SELL", 0.01, debate_triggered=True, signal_no_debate="BUY"),   # đúng -> sai
        day("BUY", 0.01, debate_triggered=True, signal_no_debate="BUY"),    # không đổi
        day("BUY", 0.01, debate_triggered=True, signal_no_debate="NEUTRAL"),  # NEUTRAL -> BUY
        day("BUY", 0.01, debate_triggered=False, signal_no_debate="BUY"),   # không có Debate: loại khỏi mẫu
    ]
    out = debate_impact(recs)
    assert out["debate_days"] == 4
    assert out["signal_changed"] == 3
    assert out["signal_change_rate"] == pytest.approx(0.75)
    assert out["wrong_to_right"] == 1
    assert out["right_to_wrong"] == 1
    assert out["neutral_to_call"] == 1
    assert out["call_to_neutral"] == 0
    assert out["net_correct_change"] == 0
    # trước Debate: SELL,BUY,BUY,NEUTRAL -> đúng 2/3 directional (SELL sai vì return>0, BUY đúng, BUY đúng)
    assert out["accuracy_before_debate"] == pytest.approx(2 / 3)
    # sau Debate: BUY,SELL,BUY,BUY -> đúng 3/4 (SELL sai vì return>0)
    assert out["accuracy_after_debate"] == pytest.approx(3 / 4)


# ---- đối chứng với dữ liệu pilot thật ---------------------------------------

PILOT = Path(__file__).parent.parent / "outputs" / "direction_pilot_retry"
DATASET = Path(__file__).parent.parent / "data" / "datasets" / "pilot_2022_01"


def _real_records():
    import csv
    returns = {r["sample_id"]: float(r["return_24h"])
               for r in csv.DictReader((DATASET / "labels.csv").read_text().splitlines())}
    records = []
    for f in sorted(PILOT.glob("days/*.json")):
        d = json.loads(f.read_text())
        sample = f.stem
        records.append({"ok": d.get("status") == "ok", "signal": d.get("signal"),
                        "return_24h": returns[sample]})
    return records


@pytest.mark.skipif(not PILOT.exists(), reason="pilot run output not present")
def test_prediction_metrics_matches_old_report():
    m = prediction_metrics(_real_records())
    assert m["requested_days"] == 30
    assert m["successful_days"] == 24
    assert m["directional_predictions"] == 24
    assert m["correct"] == 13
    assert m["directional_accuracy"] == pytest.approx(13 / 24)
    assert m["coverage"] == pytest.approx(24 / 30)


@pytest.mark.skipif(not PILOT.exists(), reason="pilot run output not present")
def test_build_records_reproduces_stored_s_final_when_no_conflict():
    """day['specialists'] là bản trước Debate; nếu ngày đó không có xung đột
    thì run_mediator lại trên đó phải ra đúng S_final đã lưu (không có gì để
    Debate thay đổi)."""
    records = build_records(PILOT, DATASET)
    ok_no_conflict = [r for r in records if r["ok"] and not r["debate_triggered"]]
    assert len(ok_no_conflict) == 18  # 24 ok - 6 debate_triggered
    for r in ok_no_conflict:
        assert r["S_final_no_debate"] == pytest.approx(r["S_final"], abs=1e-6)
        assert r["signal_no_debate"] == r["signal"]


@pytest.mark.skipif(not PILOT.exists(), reason="pilot run output not present")
def test_simulate_trades_runs_on_real_pilot_without_crashing():
    records = build_records(PILOT, DATASET)
    prices = prices_from_records(records)
    sim = simulate_trades(records, prices, fee=0.001)
    assert sim["trade_count"] >= 1
    assert len(sim["equity_curve"]) == len(records) + 1
    assert 0.0 <= sim["max_drawdown"] <= 1.0
    # 6 ngày lỗi rải rác cắt chuỗi 24 ngày SELL thành 6 đoạn liên tiếp -> 6 lệnh, đều short
    assert sim["trade_count"] == 6
    assert all(t["side"] == "short" for t in sim["trades"])


@pytest.mark.skipif(not PILOT.exists(), reason="pilot run output not present")
def test_conflict_and_s_final_buckets_on_real_pilot():
    records = build_records(PILOT, DATASET)
    cs = conflict_score_summary(records)
    assert cs["scored_days"] == 24
    assert cs["debate_triggered_days"] == 6
    assert cs["debate_trigger_rate"] == pytest.approx(6 / 24)
    buckets = s_final_buckets(records)
    assert sum(b["count"] for b in buckets) == 24  # tất cả 24 ngày SELL rơi vào các khoảng SELL


@pytest.mark.skipif(not PILOT.exists(), reason="pilot run output not present")
def test_debate_impact_on_real_pilot_no_signal_changed():
    """Đã biết từ trước: 6 ngày có Debate nhưng không ngày nào đổi tín hiệu cuối."""
    records = build_records(PILOT, DATASET)
    out = debate_impact(records)
    assert out["debate_days"] == 6
    assert out["signal_changed"] == 0
    assert out["signal_change_rate"] == 0.0
    assert out["accuracy_before_debate"] == out["accuracy_after_debate"]
