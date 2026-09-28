# Đánh giá v0 — 4 cấu hình trên cùng dữ liệu

Trạng thái các ngày: {"ok": 28, "rejected_by_reviewer": 2}

## Chất lượng dự đoán

| Cấu hình | Ngày hợp lệ | BUY/SELL | Đúng | Directional accuracy | Coverage | NEUTRAL |
|---|---|---|---|---|---|---|
| Luôn BUY | 30/30 | 30 | 14 | 46.7% | 100.0% | 0 |
| Luôn SELL | 30/30 | 30 | 16 | 53.3% | 100.0% | 0 |
| Không Debate | 28/30 | 13 | 8 | 61.5% | 43.3% | 15 |
| Đầy đủ (có Debate) | 28/30 | 13 | 8 | 61.5% | 43.3% | 15 |

## Tài chính mô phỏng (vốn đầu 1.0)

| Cấu hình | Phí/chiều | Lợi suất tích lũy | Số lệnh | Win rate | Profit factor | Max drawdown |
|---|---|---|---|---|---|---|
| Luôn BUY | 0.0% | -18.0% | 1 | 0.0% | 0.00 | 26.5% |
| Luôn BUY | 0.1% | -18.2% | 1 | 0.0% | 0.00 | 26.5% |
| Luôn BUY | 0.2% | -18.4% | 1 | 0.0% | 0.00 | 26.5% |
| Luôn SELL | 0.0% | 18.0% | 1 | 100.0% | no_losing_trades | 5.4% |
| Luôn SELL | 0.1% | 17.8% | 1 | 100.0% | no_losing_trades | 5.4% |
| Luôn SELL | 0.2% | 17.6% | 1 | 100.0% | no_losing_trades | 5.4% |
| Không Debate | 0.0% | 25.4% | 8 | 62.5% | 7.08 | 2.6% |
| Không Debate | 0.1% | 23.4% | 8 | 62.5% | 5.87 | 3.1% |
| Không Debate | 0.2% | 21.5% | 8 | 62.5% | 4.95 | 3.6% |
| Đầy đủ (có Debate) | 0.0% | 25.4% | 8 | 62.5% | 7.08 | 2.6% |
| Đầy đủ (có Debate) | 0.1% | 23.4% | 8 | 62.5% | 5.87 | 3.1% |
| Đầy đủ (có Debate) | 0.2% | 21.5% | 8 | 62.5% | 4.95 | 3.6% |

### Ba ngày vốn giảm mạnh nhất (phí 0.1%)

- Luôn BUY: 2022-01-21 (-10.4%), 2022-01-05 (-5.2%), 2022-01-22 (-3.8%)
- Luôn SELL: 2022-01-01 (-3.4%), 2022-01-12 (-2.4%), 2022-01-23 (-2.0%)
- Không Debate: 2022-01-11 (-2.3%), 2022-01-24 (-1.3%), 2022-01-14 (-1.1%)
- Đầy đủ (có Debate): 2022-01-11 (-2.3%), 2022-01-24 (-1.3%), 2022-01-14 (-1.1%)

## Tác động Debate

- Ngày có Debate hợp lệ: 0; đổi tín hiệu: 0 (sai→đúng 0, đúng→sai 0, BUY/SELL→NEUTRAL 0, NEUTRAL→BUY/SELL 0).
- Accuracy toàn lịch: không Debate 61.5%, có Debate 61.5%; coverage 43.3% → 43.3%.

Ngày specialist có cả BUY và SELL:

- 2022-01-13: conflict 0.3934, Debate không
- 2022-01-15: conflict 0.3798, Debate không
- 2022-01-21: conflict 0.3934, Debate không
- 2022-01-28: conflict 0.3934, Debate không

## Giới hạn

- Đánh giá sơ bộ trên 30 ngày tháng 1/2022: không phải tập kiểm tra độc lập (prompt/ngưỡng được phát triển trên chính giai đoạn này).
- Chỉ một giai đoạn thị trường (BTC giảm mạnh); baseline luôn SELL được lợi thế.
- Mẫu nhỏ: chênh lệch vài ngày đúng/sai chưa có ý nghĩa thống kê.
- Model có thể đã biết diễn biến giá 2022 từ dữ liệu huấn luyện.
- Mô phỏng lý tưởng: độ trễ bằng 0, bỏ trượt giá, funding và chi phí vay short.
