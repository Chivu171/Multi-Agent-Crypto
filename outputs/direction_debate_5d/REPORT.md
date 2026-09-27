# Kết quả thử hướng giá BTC 24 giờ

Win rate ở đây là directional accuracy, không phải lợi nhuận giao dịch.

```json
{
  "requested_days": 5,
  "successful_days": 5,
  "failed_or_not_run_days": 0,
  "directional_predictions": 3,
  "correct": 2,
  "directional_win_rate": 0.6666666666666666,
  "neutral_days": 2,
  "coverage_over_requested": 0.6,
  "coverage_over_successful": 0.6,
  "status_counts": {
    "ok": 5
  },
  "BUY": {
    "count": 0,
    "correct": 0,
    "accuracy": null
  },
  "SELL": {
    "count": 3,
    "correct": 2,
    "accuracy": 0.6666666666666666
  }
}
```

| Ngày | Trạng thái | Nguyên nhân | Tín hiệu |
|---|---|---|---|
| 2022-01-02 | ok |  | NEUTRAL |
| 2022-01-06 | ok |  | NEUTRAL |
| 2022-01-13 | ok |  | SELL |
| 2022-01-15 | ok |  | SELL |
| 2022-01-21 | ok |  | SELL |

Giới hạn:
- ForexFactory schedule, forecast and previous are retrospective source values assumed known before prediction; historical vintages/revisions unverified. Actual/revision/result annotations excluded.
- Global long/short uses the 5m archive column, not live period=1d; empty source cells remain missing.
- Funding is last settled rate, not a historical premiumIndex snapshot of lastFundingRate.
- On-chain and Fear & Greed publication times remain assumed; source vintages are unverified.
- Daily closed-candle evaluation differs from live intraday/current-candle fetching.
- This remains the base pilot's time split, not an independent held-out evaluation.
- Historical LLM knowledge contamination possible.
- Các ngày chọn trước theo đặc điểm đầu vào để kiểm tra pipeline; không phải mẫu ngẫu nhiên hay backtest tài chính liên tục.
- Chỉ chấm ngày có status ok (đủ 3 specialist, RCA/Debate đạt kiểm tra); NEUTRAL không tính vào mẫu số win rate.
