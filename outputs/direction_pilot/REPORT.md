# Kết quả thử hướng giá BTC 24 giờ

Win rate ở đây là directional accuracy, không phải lợi nhuận giao dịch.

```json
{
  "requested_days": 30,
  "successful_days": 3,
  "failed_or_not_run_days": 27,
  "directional_predictions": 3,
  "correct": 2,
  "directional_win_rate": 0.6666666666666666,
  "neutral_days": 0,
  "coverage_over_requested": 0.1,
  "coverage_over_successful": 1.0,
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

Giới hạn:
- 30-day train pilot, not held-out test
- Forex, funding and long/short unavailable
- Historical LLM knowledge contamination possible
- On-chain/F&G publication lags assumed
- Chỉ chấm ngày đủ 3 specialist và không có lỗi LLM ở validator/debate; NEUTRAL không tính vào mẫu số win rate.
