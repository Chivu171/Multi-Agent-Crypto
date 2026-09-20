# Giải thích dataset và nguồn gốc dữ liệu

Đây là bộ thử 30 ngày (01–30/01/2022), một mẫu lúc 00:00 UTC = 07:00 Việt Nam, dự báo lợi suất 24 giờ tiếp theo. Không có dữ liệu LLM sinh ra trong bộ này. Dữ liệu giả trong `tests/` chỉ dùng kiểm thử, không được đọc bởi script thu thập dataset.

**Kết quả kiểm chứng trực tiếp ngày 17/09/2026:** tải mới 12 request từ nguồn, khớp 130 nến Binance, 521 điểm on-chain (131 + 131 + 131 + 128), 3.147 giá trị F&G và 506 bản ghi ForexFactory đã trích. Tất cả feature số và 30 nhãn cũng được tính lại từ raw bằng script audit riêng, kết quả khớp. Hai ô trống được giữ nguyên. Xem [báo cáo tải lại nguồn](audit/20260917T082100435161Z/report.json). Kết quả này kiểm chứng nguồn/phép tính, không xác nhận giả định thời điểm công bố lịch sử.

## Mỗi file được tạo như thế nào?

| File/thư mục | Vai trò | Cách tạo |
|---|---|---|
| `raw/*.body` | Bằng chứng tải nguồn | Lưu nguyên bytes phản hồi HTTP: JSON API hoặc HTML ForexFactory, không sửa nội dung |
| `raw/*.json` | Metadata của từng phản hồi | Script ghi URL, query, URL phản hồi, HTTP status, thời điểm tải, SHA256 và tên `.body` tương ứng; đây là metadata do chương trình ghi |
| `source_data.json` | Tập hợp nguồn đã đọc | JSON-decode các raw API; giữ danh sách nến, các điểm on-chain, Fear & Greed, lỗi và danh sách raw response |
| `features.csv` | X cho ML | Với mỗi ngày, chọn dữ liệu hợp lệ theo cutoff, rồi tính chỉ báo bằng công thức; không chứa giá tương lai hoặc nhãn |
| `labels.csv` | y / ground truth | Lấy hai giá đóng cửa thực tế từ Binance, tính lợi suất 24h, phân lớp với biên ±1% |
| `snapshots.jsonl` | Snapshot cho luồng agent lịch sử | Chuyển features thành JSON, thêm 90 nến đã đóng và evidence có timestamp; mỗi dòng một mẫu; chưa tự nối vào specialist |
| `splits.csv` | Chia train/validation/test | Phân theo ngày với ranh giới cố định và cờ eligible; toàn bộ pilot hiện thuộc train |
| `sample_audit.json` | Giải thích từng ngày được giữ/loại | Sinh từ quá trình build: có đủ cửa sổ nến, nhãn và nguồn hay không |
| `quality_report.json` | Thống kê chất lượng | Đếm số mẫu, nhãn, ô thiếu, nguồn lỗi, tình trạng Forex |
| `review_10_samples_WITH_LABELS.json` | Đối chiếu thủ công | Ghép 10 snapshot đầu với nhãn thật để người đọc kiểm tra; tuyệt đối không làm đầu vào LLM |
| `forex_events_RETROSPECTIVE_ONLY.json` | Lịch sử sự kiện tách riêng | Trích JSON nhúng trong HTML ForexFactory: tên, ID, epoch, currency, impact, Actual/Forecast/Previous/Revision; chưa đưa vào features |
| `dataset_manifest.json` | Định nghĩa phiên bản dataset | Script ghi cấu hình, ngưỡng, độ trễ, hash dữ liệu và code, nguồn và raw metadata |
| `VERIFY.md` | Bản xem nhanh | Script tổng hợp thống kê và bảng 10 mẫu đầu từ các file trên |
| `audit/<thời điểm>/report.json` | Kết quả kiểm chứng độc lập | Script audit kiểm tra hash, tính lại đặc trưng/nhãn từ raw; với `--live` tải lại nguồn để đối chiếu |
| `audit/<thời điểm>/raw/` | Bằng chứng đối chiếu mới | Phản hồi HTTP được tải mới trong lần verify, tách khỏi raw gốc |
| `FILE_GUIDE.md` | Tài liệu bạn đang đọc | Giải thích nguồn và công thức, không phải dữ liệu đầu vào |

`features.csv` ghép với `labels.csv` bằng `sample_id`. Không dùng `sample_id`, `prediction_time` như biến số đầu vào ML mặc định. Không trộn file review/labels/Forex hồi cứu vào prompt.

## Các cột trong features.csv

Các tỷ lệ trả về dạng thập phân: `0.01 = 1%`, không phải `0.01%`.

| Cột | Nghĩa và đơn vị | Nguồn/công thức |
|---|---|---|
| `sample_id` | Ngày dự báo UTC | Lịch mẫu do script tạo |
| `prediction_time` | Mốc dự báo, ISO UTC | 00:00 của ngày mẫu |
| `close` | Giá BTC bằng USDT | Close nến vừa kết thúc, **không phải close cuối ngày mang tên sample_id** |
| `return_1d`, `return_7d`, `return_30d` | Lợi suất quá khứ | `close / close_lag - 1` |
| `ema20_gap`, `ema50_gap` | Khoảng cách tương đối tới EMA | `close / EMA - 1`; EMA seed SMA, tính trên 90 nến |
| `rsi14` | Chỉ số 0–100 | RSI kiểu Cutler: trung bình gain/loss 14 biến động ngày; không phải RSI Wilder |
| `volatility_7d`, `volatility_30d` | Biến động lợi suất ngày | Độ lệch chuẩn tổng thể (`ddof=0`), chưa annualize |
| `volume` | Khối lượng BTC trong nến vừa đóng | Base asset volume của Binance, **không phải USD/USDT** |
| `volume_change_1d` | Thay đổi khối lượng | `volume / volume_previous - 1` |
| `hash_rate_value` | Ước tính hashrate mạng, TH/s | Blockchain.com chart `hash-rate` |
| `miners_revenue_value` | Doanh thu thợ đào ngày, USD | Chart `miners-revenue`, gồm block rewards và transaction fees |
| `n_transactions_value` | Số giao dịch xác nhận/ngày | Chart `n-transactions` |
| `estimated_transaction_volume_usd_value` | Ước tính giá trị giao dịch on-chain, USD | Chart `estimated-transaction-volume-usd`; không phải volume trên sàn, không phải whale inflow |
| `fear_greed_value` | Chỉ số 0–100 | Alternative.me, không dùng LLM suy đoán |

Mỗi nhóm trong 5 nhóm cuối có cùng hậu tố:

| Hậu tố | Nghĩa |
|---|---|
| `_change_1d`, `_change_7d` | Với on-chain: tỷ lệ thay đổi so đúng 1/7 ngày trước. Với F&G: **chênh lệch điểm**, không phải tỷ lệ |
| `_mean_7d` | Trung bình 7 ngày liên tục; thiếu một ngày thì để trống |
| `_age_hours` | Số giờ từ `available_at` giả định đến giờ dự báo; **không phải tuổi kể từ ngày quan sát** |
| `_missing` | 1 khi không có điểm nguồn đủ điều kiện; 0 khi có điểm nguồn. 0 không bảo đảm mọi đặc trưng dẫn xuất đều đầy đủ |

Ví dụ `_age_hours=0` cho on-chain ngày 30/12 tại dự báo 01/01 chỉ có nghĩa timestamp + 2 ngày vừa chạm cutoff. Nó không có nghĩa dữ liệu được quan sát hoặc tải ngay lúc đó.

## Lấy dữ liệu từ đâu?

1. **Binance:** `https://data-api.binance.vision/api/v3/klines`, BTCUSDT, `interval=1d`, `startTime`/`endTime` UTC, `limit=1000`. Pilot raw có 130 nến từ 23/09/2021 đến 30/01/2022: gồm warmup và nến dùng tạo nhãn. Lấy 100 ngày warmup, mỗi feature window dùng 90 ngày.
2. **Blockchain.com:** `https://api.blockchain.info/charts/<chart>`, `start=2021-09-23`, `timespan=130days`, `sampled=false`, JSON. Ba chart có 131 điểm, chart transaction-volume có 128 điểm trong phản hồi gốc. Dữ liệu nguồn có thể bao gồm điểm biên, builder chọn theo timestamp.
3. **Alternative.me:** `https://api.alternative.me/fng/?limit=0&format=json`, lấy toàn bộ lịch sử sẵn có rồi chọn quá khứ theo cutoff. Raw gốc có 3.147 điểm, không có nghĩa tất cả được đưa vào 30 mẫu. Snapshot không chứa các điểm tương lai.
4. **ForexFactory:** `https://www.forexfactory.com/calendar?week=...`, 6 tuần từ `dec26.2021` đến `jan30.2022`. Parse mảng JSON có sẵn trong HTML; UTC lấy từ epoch `dateline`, không tự đoán từ giờ hiển thị. Thu được 506 bản ghi, gồm các ngày ngoài pilot; 46 bản ghi USD High/Medium nằm trong 30 ngày yêu cầu.

Các tên/đơn vị on-chain nêu trên được đối chiếu với `name`, `unit`, `period`, `description` trong raw JSON. “Ước tính” là bản chất chỉ số của nhà cung cấp; không phải số tự bịa bởi script.

## Nhãn là gì? Có phải tự tạo không?

**Giá là dữ liệu nguồn. Nhãn BUY/SELL/NEUTRAL là biến được tính bằng quy tắc do mình đề xuất và ghi rõ.** Nhà cung cấp không trả nhãn “nên mua/bán”.

Ví dụ 01/01/2022 00:00 UTC:

- Giá tham chiếu: close 31/12/2021 = **46.216,93 USDT**.
- Giá mục tiêu: close 01/01/2022 = **47.722,65 USDT**.
- Lợi suất = `47722.65 / 46216.93 - 1` = **3,25794%**.
- Vì > 1%, nhãn theo định nghĩa dataset là **BUY**.

Giá mục tiêu chỉ nằm trong labels/review, không nằm trong snapshot tại ngày này. Đây là nhãn mô tả biến động tương lai 24h, không phải khẳng định giao dịch có lãi sau chi phí.

## Chuẩn đến mức nào?

- Có thể kiểm chứng **nguồn gốc và phép tính**: raw response, URL, checksum; tải mới từ provider; tính lại tất cả feature bằng implementation audit riêng, không gọi builder để tự xác nhận chính nó.
- **Độ trễ on-chain 2 ngày, F&G 1 ngày là giả định**, không phải giờ công bố lịch sử được nhà cung cấp xác nhận. Trường `available_at` được tính, không được tải sẵn.
- Chưa xác minh lịch sử chỉnh sửa/vintage. Dữ liệu tải hôm nay có thể khác thứ thực sự được công bố năm 2022. Tải lại cùng ngày cho kết quả khớp không giải quyết vấn đề này.
- ForexFactory được giữ ngoài feature matrix vì chưa xác minh tính sẵn có tại thời điểm dự báo.
- Hai ô thiếu được giữ nguyên: mean_7d của estimated volume ở 01/01 và change_7d ở 02/01. Không bịa giá trị để làm bảng đầy đủ.
- Test pass xác nhận hành vi phần mềm trên các trường hợp kiểm thử; kiểm tra nguồn trực tiếp được ghi riêng trong `audit/`.

## Tự chạy lại kiểm chứng

```bash
python -m scripts.verify_dataset_sources
python -m scripts.verify_dataset_sources --live
```

Lệnh đầu không gọi mạng. Lệnh sau tải lại 12 request từ các URL và query gốc, lưu phản hồi mới và báo mọi khác biệt/lỗi. Không sửa dataset gốc. Báo cáo `live_requested=false` chỉ là audit nội bộ; không đọc nó như chứng cứ đã tải mới.

Tài liệu nguồn: [Binance](https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints), [Blockchain.com](https://www.blockchain.com/en/explorer/api/charts_api), [Alternative.me](https://alternative.me/crypto/fear-and-greed-index/), [ForexFactory](https://www.forexfactory.com/calendar).
