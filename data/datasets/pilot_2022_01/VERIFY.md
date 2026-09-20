# Kiểm tra dataset BTC lịch sử

Khoảng dự báo: 2022-01-01 → 2022-01-30 (00:00 UTC, 24 giờ).
Số ngày yêu cầu: 30; có nhãn: 30; đủ nguồn core và split hợp lệ: 30.

**Chưa có mẫu đủ toàn bộ nguồn của live pipeline. ForexFactory bị loại khỏi features.**

Lịch ForexFactory: trích 506 bản ghi; 46 sự kiện USD High/Medium trong khoảng yêu cầu.
Xem `forex_events_RETROSPECTIVE_ONLY.json`: có Actual/Forecast/Previous, chỉ dùng kiểm tra lịch sử, không đưa vào prompt.
Số mẫu không thiếu bất kỳ feature nào: 28. Ô trống được giữ nguyên, không tự nội suy.

Phân bố nhãn: {'BUY': 8, 'SELL': 10, 'NEUTRAL': 12}

## Kiểm tra thủ công

1. Mở `review_10_samples_WITH_LABELS.json`; đối chiếu 10 mẫu đầu với source_data.json và raw/.
2. Kiểm tra available_at ≤ prediction_time; nến market đều đã đóng, không có nến mục tiêu trong snapshot.
3. Tính lại future_price / reference_price - 1 và nhãn ±1% (hoặc ngưỡng trong manifest).
4. Xem sample_audit.json, missing_cells và forex_audit trong quality_report.json.
5. Không đưa file review hay labels vào prompt hoặc feature matrix.

## Giới hạn

- On-chain and Fear & Greed publication times are assumed, not verified historical vintages.
- Forex fields excluded; this is NOT the full live pipeline dataset.
- Funding and long/short ratio not included.
- Historical LLM evaluation may contain knowledge from model pretraining.
- Close-to-close prediction labels do not imply executable trading returns.

## 10 mẫu đầu để đối chiếu

| Ngày dự báo (00:00 UTC) | Giá tham chiếu | Giá sau 24h | Lợi suất | Nhãn | On-chain quan sát lúc | F&G quan sát lúc |
|---|---:|---:|---:|---|---|---|
| 2022-01-01 | 46216.93 | 47722.65 | 3.2579% | BUY | 2021-12-30T00:00:00+00:00 | 2021-12-31T00:00:00+00:00 |
| 2022-01-02 | 47722.65 | 47286.18 | -0.9146% | NEUTRAL | 2021-12-31T00:00:00+00:00 | 2022-01-01T00:00:00+00:00 |
| 2022-01-03 | 47286.18 | 46446.10 | -1.7766% | SELL | 2022-01-01T00:00:00+00:00 | 2022-01-02T00:00:00+00:00 |
| 2022-01-04 | 46446.10 | 45832.01 | -1.3222% | SELL | 2022-01-02T00:00:00+00:00 | 2022-01-03T00:00:00+00:00 |
| 2022-01-05 | 45832.01 | 43451.13 | -5.1948% | SELL | 2022-01-03T00:00:00+00:00 | 2022-01-04T00:00:00+00:00 |
| 2022-01-06 | 43451.13 | 43082.31 | -0.8488% | NEUTRAL | 2022-01-04T00:00:00+00:00 | 2022-01-05T00:00:00+00:00 |
| 2022-01-07 | 43082.31 | 41566.48 | -3.5185% | SELL | 2022-01-05T00:00:00+00:00 | 2022-01-06T00:00:00+00:00 |
| 2022-01-08 | 41566.48 | 41679.74 | 0.2725% | NEUTRAL | 2022-01-06T00:00:00+00:00 | 2022-01-07T00:00:00+00:00 |
| 2022-01-09 | 41679.74 | 41864.62 | 0.4436% | NEUTRAL | 2022-01-07T00:00:00+00:00 | 2022-01-08T00:00:00+00:00 |
| 2022-01-10 | 41864.62 | 41822.49 | -0.1006% | NEUTRAL | 2022-01-08T00:00:00+00:00 | 2022-01-09T00:00:00+00:00 |

## Lỗi nguồn

{}
