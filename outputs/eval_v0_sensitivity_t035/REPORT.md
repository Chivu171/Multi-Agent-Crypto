# Kết quả thử hướng giá BTC 24 giờ

Win rate ở đây là directional accuracy, không phải lợi nhuận giao dịch.

```json
{
  "requested_days": 30,
  "successful_days": 14,
  "failed_or_not_run_days": 16,
  "directional_predictions": 4,
  "correct": 1,
  "directional_win_rate": 0.25,
  "neutral_days": 10,
  "coverage_over_requested": 0.13333333333333333,
  "coverage_over_successful": 0.2857142857142857,
  "status_counts": {
    "ok": 14,
    "api_error": 1,
    "not_run_quota": 15
  },
  "BUY": {
    "count": 0,
    "correct": 0,
    "accuracy": null
  },
  "SELL": {
    "count": 4,
    "correct": 1,
    "accuracy": 0.25
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
| 2022-01-13 | ok |  | NEUTRAL |
| 2022-01-14 | ok |  | SELL |
| 2022-01-15 | api_error | quota |  |
| 2022-01-16 | not_run_quota | quota |  |
| 2022-01-17 | not_run_quota | quota |  |
| 2022-01-18 | not_run_quota | quota |  |
| 2022-01-19 | not_run_quota | quota |  |
| 2022-01-20 | not_run_quota | quota |  |
| 2022-01-21 | not_run_quota | quota |  |
| 2022-01-22 | not_run_quota | quota |  |
| 2022-01-23 | not_run_quota | quota |  |
| 2022-01-24 | not_run_quota | quota |  |
| 2022-01-25 | not_run_quota | quota |  |
| 2022-01-26 | not_run_quota | quota |  |
| 2022-01-27 | not_run_quota | quota |  |
| 2022-01-28 | not_run_quota | quota |  |
| 2022-01-29 | not_run_quota | quota |  |
| 2022-01-30 | not_run_quota | quota |  |

Giới hạn:
- ForexFactory schedule, forecast and previous are retrospective source values assumed known before prediction; historical vintages/revisions unverified. Actual/revision/result annotations excluded.
- Global long/short uses the 5m archive column, not live period=1d; empty source cells remain missing.
- Funding is last settled rate, not a historical premiumIndex snapshot of lastFundingRate.
- On-chain and Fear & Greed publication times remain assumed; source vintages are unverified.
- Daily closed-candle evaluation differs from live intraday/current-candle fetching.
- This remains the base pilot's time split, not an independent held-out evaluation.
- Historical LLM knowledge contamination possible.
- Chỉ chấm ngày có status ok (đủ 3 specialist, RCA/Debate đạt kiểm tra); NEUTRAL không tính vào mẫu số win rate.
