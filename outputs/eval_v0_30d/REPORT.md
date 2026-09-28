# Kết quả thử hướng giá BTC 24 giờ

Win rate ở đây là directional accuracy, không phải lợi nhuận giao dịch.

```json
{
  "requested_days": 30,
  "successful_days": 28,
  "failed_or_not_run_days": 2,
  "directional_predictions": 13,
  "correct": 8,
  "directional_win_rate": 0.6153846153846154,
  "neutral_days": 15,
  "coverage_over_requested": 0.43333333333333335,
  "coverage_over_successful": 0.4642857142857143,
  "status_counts": {
    "ok": 28,
    "rejected_by_reviewer": 2
  },
  "BUY": {
    "count": 2,
    "correct": 2,
    "accuracy": 1.0
  },
  "SELL": {
    "count": 11,
    "correct": 6,
    "accuracy": 0.5454545454545454
  }
}
```

| Ngày | Trạng thái | Nguyên nhân | Tín hiệu |
|---|---|---|---|
| 2022-01-01 | ok |  | NEUTRAL |
| 2022-01-02 | ok |  | NEUTRAL |
| 2022-01-03 | ok |  | NEUTRAL |
| 2022-01-04 | ok |  | NEUTRAL |
| 2022-01-05 | ok |  | SELL |
| 2022-01-06 | ok |  | NEUTRAL |
| 2022-01-07 | ok |  | NEUTRAL |
| 2022-01-08 | ok |  | NEUTRAL |
| 2022-01-09 | ok |  | SELL |
| 2022-01-10 | ok |  | NEUTRAL |
| 2022-01-11 | ok |  | SELL |
| 2022-01-12 | ok |  | NEUTRAL |
| 2022-01-13 | ok |  | SELL |
| 2022-01-14 | ok |  | SELL |
| 2022-01-15 | ok |  | SELL |
| 2022-01-16 | ok |  | SELL |
| 2022-01-17 | ok |  | NEUTRAL |
| 2022-01-18 | rejected_by_reviewer | review_rejected |  |
| 2022-01-19 | ok |  | NEUTRAL |
| 2022-01-20 | ok |  | SELL |
| 2022-01-21 | ok |  | SELL |
| 2022-01-22 | ok |  | SELL |
| 2022-01-23 | ok |  | BUY |
| 2022-01-24 | ok |  | SELL |
| 2022-01-25 | ok |  | NEUTRAL |
| 2022-01-26 | ok |  | NEUTRAL |
| 2022-01-27 | ok |  | NEUTRAL |
| 2022-01-28 | ok |  | BUY |
| 2022-01-29 | ok |  | NEUTRAL |
| 2022-01-30 | rejected_by_reviewer | review_rejected |  |

Giới hạn:
- ForexFactory schedule, forecast and previous are retrospective source values assumed known before prediction; historical vintages/revisions unverified. Actual/revision/result annotations excluded.
- Global long/short uses the 5m archive column, not live period=1d; empty source cells remain missing.
- Funding is last settled rate, not a historical premiumIndex snapshot of lastFundingRate.
- On-chain and Fear & Greed publication times remain assumed; source vintages are unverified.
- Daily closed-candle evaluation differs from live intraday/current-candle fetching.
- This remains the base pilot's time split, not an independent held-out evaluation.
- Historical LLM knowledge contamination possible.
- Chỉ chấm ngày có status ok (đủ 3 specialist, RCA/Debate đạt kiểm tra); NEUTRAL không tính vào mẫu số win rate.
