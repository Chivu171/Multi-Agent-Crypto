# Dataset lịch sử BTC — kế hoạch và bản thử để kiểm tra

## Phạm vi đã triển khai

- Một mẫu mỗi ngày tại **00:00 UTC (07:00 Việt Nam)**, dự báo **24 giờ** tiếp theo.
- Bản thử: **01–30/01/2022**, 30 mẫu thật lấy từ các nguồn công khai, không dùng LLM để tạo dữ liệu hay nhãn.
- Mục tiêu sau khi kiểm tra bản thử: 01/01/2022–31/12/2025, 1.461 ngày danh nghĩa.
- Bản core có OHLCV + 4 chỉ số on-chain + Fear & Greed. **Chưa phải bộ đủ đầu vào của live pipeline**: ForexFactory chưa có phiên bản chứng minh thông tin đã biết lúc dự báo; funding rate và long/short ratio chưa thu thập.
- Code chạy tách khỏi `main.py`; chưa huấn luyện ML, chưa gọi agent, chưa thực hiện backtest.

## Chạy và tái lập

Từ thư mục gốc, sau khi cài dependency của project:

```bash
python -m scripts.build_dataset --start 2022-01-01 --end 2022-01-30 --forex
python -m scripts.build_dataset --start 2022-01-01 --end 2022-01-30 --forex --offline
```

Output mặc định: `data/datasets/pilot_2022_01/`. Lần đầu tải dữ liệu, các lần sau dùng `source_data.json` và kiểm tra checksum raw; `--offline` không gửi request. Muốn tải lại nguồn hoặc đổi khoảng ngày, dùng thư mục `--output` mới. Lỗi HTTP đã được lưu không bị âm thầm thay bằng dữ liệu mới.

Ví dụ mở rộng sau khi đã kiểm tra phương pháp:

```bash
python -m scripts.build_dataset --start 2022-01-01 --end 2025-12-31 --forex --output data/datasets/btc_daily_2022_2025
```

`--forex` tải trang lịch theo tuần, trích bản ghi sự kiện để kiểm tra; không tự đưa chúng vào feature matrix. Có thể chạy không có cờ này để xây core. Mở rộng toàn kỳ chưa được thực hiện trong bước bản thử.

## Quy tắc thời gian từng nguồn

| Nguồn | Thông tin | Quy tắc |
|---|---|---|
| Binance spot BTCUSDT | OHLCV nến `1d` UTC | Lấy đúng 90 nến liên tục đã đóng trước/tại mốc dự báo; không lấy nến mở tại mốc dự báo vào features |
| Blockchain.com Charts | `hash-rate`, `miners-revenue`, `n-transactions`, `estimated-transaction-volume-usd` | `available_at = timestamp nguồn + 2 ngày` (giả định, chưa xác minh vintage) |
| Alternative.me | Fear & Greed | `available_at = timestamp nguồn + 1 ngày` (giả định, chưa xác minh vintage) |
| ForexFactory | Lịch sự kiện lịch sử | Lưu epoch `dateline` dưới dạng UTC, cờ thời gian ẩn/tentative và giờ hiển thị gốc; `available_at = null`, không dùng cho dự báo chính |

Các ngày on-chain là timestamp do nhà cung cấp trả về. Cộng độ trễ không chứng minh số liệu chưa bị sửa sau đó. Có thể tăng độ trễ bằng `--onchain-lag-days` / `--fear-greed-lag-days` để phân tích độ nhạy; code không cho giảm dưới giả định bảo thủ mặc định.

As-of join chọn bản ghi mới nhất có `available_at <= prediction_time`; chỉ giữ bản ghi tối đa 72 giờ từ `available_at`. Snapshot giữ cả `observed_at`, `available_at`, tuổi dữ liệu và giả định. Thời điểm tải thực tế, URL, query và checksum nằm trong raw metadata/manifest, không giả làm thời điểm công bố.

## Đặc trưng

- Market: giá đóng cửa, lợi suất 1/7/30 ngày, khoảng cách giá với EMA20/50, RSI14 kiểu Cutler, độ lệch chuẩn lợi suất 7/30 ngày (`ddof=0`), volume và thay đổi volume một ngày.
- EMA dùng SMA để khởi tạo trên cửa sổ 90 nến cố định; cách lấy cửa sổ này phải giữ nhất quán giữa train và test. Live code trước đây dùng 60 nến, chưa tự sửa theo dataset.
- On-chain: giá trị mới nhất đủ điều kiện, thay đổi tỷ lệ đúng 1/7 ngày, trung bình 7 ngày lịch liên tục, tuổi dữ liệu và cờ thiếu. Không nhầm hai điểm cách nhiều ngày là thay đổi một ngày.
- Fear & Greed: giá trị, thay đổi **điểm chỉ số** 1/7 ngày, trung bình 7 ngày, tuổi dữ liệu và cờ thiếu.
- Không scale hay impute ở bước dựng dataset. Khi train, chỉ fit các phép này trên train của từng lần chia.

Không dùng `sample_id` hoặc `prediction_time` làm đặc trưng ML mặc định. Giá thị trường chỉ là một trong các đặc trưng; các baseline nên được đánh giá riêng với cùng tập ngày hợp lệ.

## ForexFactory: dữ liệu có gì và chưa chứng minh gì

Parser đọc mảng JSON nhúng trong HTML, không chạy JavaScript, không suy ra UTC từ giờ hiển thị theo vị trí truy cập. Nó giữ tên, currency, impact, event_id, epoch, Actual, Forecast, Previous và Revision trong file riêng **RETROSPECTIVE_ONLY**.

- Trang có chặn/challenge hoặc thay đổi cấu trúc được báo lỗi; không coi đó là lịch không có sự kiện.
- Các sự kiện có thời gian ẩn, cả ngày hoặc tentative giữ nguyên cờ; epoch không bảo đảm một giờ công bố chính xác cho những sự kiện đó.
- Lịch tải hiện tại có thể đã điều chỉnh; không đưa Actual trước giờ công bố, cũng không khẳng định Forecast/Previous đã có lúc dự báo.
- Các trường lịch tương lai (số sự kiện 24 giờ tới, giờ đến CPI/FOMC...) chưa được dựng thành features vì chưa xác minh phiên bản lịch đã biết lúc đó.
- Bản thử tải 6 tuần bao quanh khoảng dự báo; vì vậy số sự kiện raw lớn hơn số sự kiện trong 30 ngày. Báo cáo đếm riêng USD High/Medium trong khoảng yêu cầu.

## Ground truth và chia tập

`P_t` = close nến kết thúc tại mốc dự báo, `P_t+24h` = close nến kế tiếp. Nhãn hồi quy: `P_t+24h / P_t - 1`.

Mặc định `--threshold 0.01`: BUY khi vượt +1%, SELL khi dưới -1%, NEUTRAL gồm hai biên. Đây là định nghĩa thử nghiệm, không phải ngưỡng đã tối ưu. Ngưỡng nhãn khác ngưỡng điểm `S_final` của mediator. Chốt ngưỡng trước khi mở test.

| Tập | Thời gian danh nghĩa | Số ngày trước kiểm tra dữ liệu/purge |
|---|---|---:|
| Train | 01/01/2022–30/06/2024 | 912 |
| Validation | 01/07/2024–31/12/2024 | 184 |
| Test | 01/01/2025–31/12/2025 | 365 |

Code đánh dấu không dùng mẫu 30/06/2024 và 31/12/2024 để nhãn không chạm mốc bắt đầu tập sau. Các phương pháp so sánh dùng cùng `sample_id` hợp lệ. Không shuffle. Dataset 30 ngày chỉ để kiểm tra pipeline, toàn bộ thuộc train, chưa chứng minh chất lượng mô hình.

Giá đóng cửa để chấm dự báo không phải cam kết có thể giao dịch đúng giá đó. Muốn tính P&L cần giá thực thi, phí và trượt giá riêng. Backtest LLM trên quá khứ vẫn có nguy cơ biết sự kiện qua pretraining.

## Kiểm tra dữ liệu và thiếu dữ liệu

- Không chấp nhận duplicate candle, giá không hữu hạn, OHLC sai quan hệ hoặc nến không đúng ngày UTC.
- Thiếu nến trong cửa sổ 90 ngày hoặc thiếu giá mục tiêu: không xuất mẫu có nhãn, ghi lý do vào audit.
- Thiếu điểm nguồn/đặc trưng: giữ ô trống, không nội suy hay backward-fill từ tương lai.
- `eligible_core` nghĩa là cả 4 chỉ số on-chain và F&G có điểm đủ tươi, **không có nghĩa mọi đặc trưng dẫn xuất đều đầy đủ**. Xem thêm `complete_feature_rows` và `missing_cells`.
- `eligible_full` hiện luôn false để tránh đánh đồng bản core với pipeline đầy đủ.
- Raw response được giữ nguyên và hash SHA256. Manifest ghi cấu hình, hash output và hash code để biết phiên bản đã tạo dataset.

## Đầu ra để bạn verify

Mở trước `data/datasets/pilot_2022_01/VERIFY.md`: có bảng 10 mẫu đầu, số liệu chất lượng và giới hạn.

| File | Mục đích |
|---|---|
| `features.csv` | Đặc trưng số cho ML, không chứa target |
| `labels.csv` | Giá tham chiếu, giá tương lai, lợi suất, nhãn |
| `snapshots.jsonl` | Đầu vào lịch sử có provenance và 90 nến đã đóng; chưa nối trực tiếp vào specialist |
| `splits.csv` | Tập train/validation/test và cờ đủ điều kiện |
| `review_10_samples_WITH_LABELS.json` | 10 mẫu kèm nhãn **chỉ để người kiểm tra**, không đưa vào LLM |
| `forex_events_RETROSPECTIVE_ONLY.json` | Sự kiện đã trích, bao gồm Actual; không dùng trong features |
| `quality_report.json`, `sample_audit.json` | Số mẫu, nhãn, ô thiếu, lỗi và lý do loại |
| `source_data.json`, `raw/`, `dataset_manifest.json` | Nguồn gốc, dữ liệu thô, tham số và kiểm tra toàn vẹn |

Trước khi mở rộng: đối chiếu 10 mẫu với giá gốc; xác nhận khung 24h, ±1%, độ trễ; quyết định có chấp nhận giả định lịch sử cho ForexFactory hay cần nguồn có vintage. Bản thử chưa đưa ra quyết định thay người dùng về việc coi lịch hồi cứu là thông tin đã biết trong quá khứ.

## Nguồn tài liệu

- [Binance Spot API](https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md)
- [Blockchain.com Charts API](https://www.blockchain.com/en/explorer/api/charts_api)
- [Alternative.me Fear & Greed API](https://alternative.me/crypto/fear-and-greed-index/)
- [ForexFactory Calendar](https://www.forexfactory.com/calendar)
