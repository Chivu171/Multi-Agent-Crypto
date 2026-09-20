# Kết quả thử hướng giá BTC 24 giờ

Win rate ở đây là directional accuracy, không phải lợi nhuận giao dịch.

```json
{
  "requested_days": 30,
  "successful_days": 24,
  "failed_or_not_run_days": 6,
  "directional_predictions": 24,
  "correct": 13,
  "directional_win_rate": 0.5416666666666666,
  "neutral_days": 0,
  "coverage_over_requested": 0.8,
  "coverage_over_successful": 1.0,
  "BUY": {
    "count": 0,
    "correct": 0,
    "accuracy": null
  },
  "SELL": {
    "count": 24,
    "correct": 13,
    "accuracy": 0.5416666666666666
  }
}
```

Giới hạn:
- 30-day train pilot, not held-out test
- Forex, funding and long/short unavailable
- Historical LLM knowledge contamination possible
- On-chain/F&G publication lags assumed
- Chỉ chấm ngày đủ 3 specialist và không có lỗi LLM ở validator/debate; NEUTRAL không tính vào mẫu số win rate.

## Kết luận lần chạy thực tế

24/30 ngày có đủ đầu ra; 13 đúng, 11 sai: **54,17% directional win rate**. Sáu ngày lỗi không được tính vào mẫu số. Coverage = 80%. Cả 24 tín hiệu đều SELL; không có BUY hoặc NEUTRAL.

Baseline luôn SELL trên cùng 24 ngày cũng đúng 13/24: chưa có lợi ích so với baseline này. Không suy ra độ chính xác BUY hoặc hiệu quả giao dịch từ kết quả này.

Có 6 ngày hợp lệ kích hoạt Debate. Một số lập luận Debate nhắc dữ liệu thiếu (ví dụ funding âm ngày 12/01), cần đánh giá riêng chất lượng bằng chứng.

## Từng ngày

| Ngày | Tín hiệu | Lợi suất thực tế 24h | Kết quả |
|---|---|---:|---|
| 2022-01-01 | SELL | 3.2579% | Sai |
| 2022-01-02 | SELL | -0.9146% | Đúng |
| 2022-01-03 | SELL | -1.7766% | Đúng |
| 2022-01-04 | SELL | -1.3222% | Đúng |
| 2022-01-05 | SELL | -5.1948% | Đúng |
| 2022-01-06 | SELL | -0.8488% | Đúng |
| 2022-01-07 | SELL | -3.5185% | Đúng |
| 2022-01-08 | — | 0.2725% | Lỗi đầu ra specialist |
| 2022-01-09 | SELL | 0.4436% | Sai |
| 2022-01-10 | SELL | -0.1006% | Đúng |
| 2022-01-11 | SELL | 2.1682% | Sai |
| 2022-01-12 | SELL | 2.7461% | Sai |
| 2022-01-13 | SELL | -3.0580% | Đúng |
| 2022-01-14 | — | 1.1745% | Lỗi API 429 |
| 2022-01-15 | SELL | 0.0565% | Sai |
| 2022-01-16 | SELL | -0.0293% | Đúng |
| 2022-01-17 | — | -2.0200% | Lỗi đầu ra specialist |
| 2022-01-18 | SELL | 0.3566% | Sai |
| 2022-01-19 | SELL | -1.6342% | Đúng |
| 2022-01-20 | — | -2.3502% | Lỗi đầu ra specialist |
| 2022-01-21 | SELL | -10.4118% | Đúng |
| 2022-01-22 | SELL | -3.7697% | Đúng |
| 2022-01-23 | — | 3.3450% | Lỗi đầu ra specialist |
| 2022-01-24 | SELL | 1.1472% | Sai |
| 2022-01-25 | SELL | 0.8128% | Sai |
| 2022-01-26 | SELL | -0.4031% | Đúng |
| 2022-01-27 | SELL | 0.9529% | Sai |
| 2022-01-28 | SELL | 1.4975% | Sai |
| 2022-01-29 | SELL | 1.1939% | Sai |
| 2022-01-30 | — | -0.7469% | Lỗi đầu ra specialist |
