# Dataset có phù hợp với hệ thống hiện tại không?

**Có để kiểm tra đầu vào và pipeline dự đoán 24 giờ; chưa đủ tương đương live hoặc làm tập kiểm tra độc lập.** Đã kiểm tra trực tiếp `data/datasets/pilot_2022_01_forecast_previous` với adapter hiện tại, không chỉ đọc báo cáo cũ.

## Kiểm chứng và cách chạy lại

Áp dụng skill diagnosing-bugs. Không tìm thấy CONTEXT.md hoặc ADR trong danh sách file repository. Bắt đầu bằng vòng kiểm tra offline trên adapter và bộ chặn full-live, chạy dưới một giây:

```sh
.venv/bin/python -m scripts.audit_dataset_compatibility \
  --output outputs/dataset_compatibility_2026_09_24/audit.json
```

Kết quả: adapter 30/30, nhãn 30/30 khớp giá Binance gốc đã lưu; 21 kiểm tra hash artifact và 96 kiểm tra hash phản hồi nguồn giữa bộ gốc/bổ sung đều khớp. Đây là kiểm tra tính toàn vẹn và số học của nguồn đã lưu, không phải lấy lại dữ liệu trực tuyến hay chứng minh vintage.

Lặp lại với `--require-full-live` cho kết quả exit 1:

```text
ValueError: Dataset is not full-live equivalent on 30 days;
inspect source_coverage.json/VERIFY.md. No evaluation started.
```

Đã thu nhỏ kiểm tra bộ chặn xuống một snapshot và lặp hai lần, cùng kết quả từ chối. Cờ eligible_full_live=False tự nó không giải thích nguyên nhân; các kiểm tra coverage, thời gian và so sánh phép tính bên dưới mới xác định khác biệt thực tế.

## Coverage và thời điểm

| Nhóm dữ liệu                                                    | Có trong snapshot | Kết luận                                                                 |
| ------------------------------------------------------------------ | -----------------: | -------------------------------------------------------------------------- |
| 4 chỉ số Blockchain.info                                         |              30/30 | Adapter đọc đủ; thời điểm khả dụng giả định trễ 2 ngày       |
| Giá/nến Binance                                                  |              30/30 | 90 nến đã đóng trong snapshot; adapter lấy 60 nến cuối             |
| Fear & Greed                                                       |              30/30 | Adapter đọc đủ; thời điểm khả dụng giả định trễ 1 ngày       |
| Funding đã thanh toán                                           |              30/30 | Không phải bản lưu historical premiumIndex giống live                 |
| Global long/short ratio                                            |              11/30 | 19 ngày thiếu, giữ null; kỳ lấy mẫu kho 5 phút khác live period=1d |
| Lịch ForexFactory                                                 |              30/30 | 25 ngày có sự kiện, 5 ngày danh sách rỗng hợp lệ                  |
| Forex có phiên bản tại thời điểm dự báo được xác minh |               0/30 | Schedule/Forecast/Previous hồi cứu, giả định đã biết trước       |

Có 226 lượt sự kiện qua 30 snapshot, 180 lượt có Forecast và 185 lượt có Previous. Đây là lượt xuất hiện, không phải số sự kiện duy nhất. Chỉ sự kiện sắp tới High/Medium trong tuần UTC được chọn, tối đa 10; Actual/Revision không đi vào đầu vào agent.

Mốc dự báo mỗi ngày 00:00 UTC, horizon 24 giờ. Cửa sổ nến đều kết thúc trước hoặc tại mốc dự báo; dữ liệu on-chain/Fear & Greed không vượt mốc theo available_at được gán. Các kiểm tra thời gian chỉ đúng **theo giả định khả dụng đã ghi**, chưa xác nhận nhà cung cấp đã công bố đúng phiên bản đó lúc bấy giờ. Việc không đưa Actual vào prompt không loại bỏ rủi ro Forecast/Previous hoặc lịch đã được sửa hồi cứu.

Live hiện đọc nến ngày cuối được API trả về mà không lọc close time; nến cuối có thể đang hình thành. Dataset dùng nến đã đóng. Do đó cùng tên chỉ số không đồng nghĩa cùng quy tắc thời điểm.

## Khác biệt EMA giữa feature ML và agent

Giả thuyết được xác nhận bằng cách giữ nguyên giá và hàm `_ema`, chỉ đổi số nến khởi tạo:

- `features.csv`: EMA20/EMA50 khởi tạo từ cửa sổ 90 nến; CSV lưu dưới dạng ema20_gap/ema50_gap.
- Adapter: tính lại EMA20/EMA50 từ 60 nến cuối để theo số nến live đang lấy.
- Cả 30 ngày có khác biệt ở cả EMA20 và EMA50. Khi tính lại từ 90 nến, kết quả khớp feature ở 30/30 ngày.
- Chênh tuyệt đối lớn nhất: EMA20 khoảng 30,31 USD; EMA50 khoảng 1.750,65 USD.
- Ví dụ 26/01: EMA50 adapter = 45.124,27 USD; EMA50 suy ra từ CSV = 45.574,78 USD.

Đây không phải giá Binance bị bịa hoặc sai số parse. Hai đường dùng cửa sổ khởi tạo khác nhau. Nếu baseline ML dùng CSV còn multi-agent dùng adapter, phải ghi nhận đầu vào kỹ thuật khác nhau; nên thống nhất cách tạo chỉ báo trước khi muốn so sánh trên cùng feature. Không sửa âm thầm dataset hoặc kết quả cũ trong đợt audit này.

## Quy mô và mục đích sử dụng

Cả 30 dòng hiện thuộc split `train`; validation/test đều 0. Bộ này phù hợp kiểm tra schema, xử lý thiếu dữ liệu, cơ chế review/debate và phép chấm hướng giá. Nó chưa phải bằng chứng tổng quát hóa, chưa đủ kết luận hệ thống tốt hơn baseline hoặc đã tương đương live.

Dataset có thể cung cấp giá/nhãn cho mô phỏng theo ngày trên lịch liên tục, nhưng kết luận tài chính còn phụ thuộc quy tắc vị thế/chi phí và các hạn chế nguồn nêu trên. Không tính tài chính bằng cách nối 5 ngày rời nhau đã chọn chạy thử.

## Phân biệt lỗi dữ liệu và lỗi hệ thống

Các giả thuyết đã đối chiếu:

1. Thiếu nguồn: xác nhận long/short thiếu 19 ngày; không phải mọi nguồn đều thiếu.
2. Khác định nghĩa/thời điểm: xác nhận EMA 90/60 nến, ratio 5m/1d, funding và giả định vintage.
3. Không khớp adapter/schema: không tái hiện ở 30 snapshot; tất cả qua hợp đồng đầu vào được kiểm tra.
4. Lỗi chạy do model/reviewer: xác nhận riêng qua log thực tế, không suy ra từ dataset.

Lượt chạy có reviewer trên Groq: 12/01 lỗi quote trong Debate; 19/01 hợp lệ SELL và đúng hướng; 20/01, 22/01 lỗi 429 do quota token/ngày, nên 26/01 không được gọi trong lượt đó. Một ngày đúng trên một ngày hợp lệ không chứng minh hệ thống cải thiện.

Khi thử tiếp, cấu hình hiện tại đã khác (validator/debate/grounding chuyển sang OpenRouter; code config/llm đổi). Không ghép kết quả vào cùng lượt cũ. Đã thử riêng 26/01 với cấu hình mới: Market trả 404 cho slug free, reviewer trả 429. Chi tiết ở `../direction_reviewed_current_config_2022_01_26/`.

## Ưu tiên tiếp theo

1. Khôi phục cấu hình model/API có thể chạy ổn định; không dùng lỗi provider để đánh giá chất lượng dataset.
2. Thống nhất một quy tắc thời điểm và cửa sổ chỉ báo giữa CSV, adapter và live, xuất phiên bản dataset mới khi đổi.
3. Với long/short, chọn cùng kỳ nguồn và chính sách thiếu dữ liệu cho tất cả phương pháp; không nội suy hoặc thay 0 để giả vờ đủ nguồn.
4. Giữ nhãn “lịch/Forecast/Previous có giả định lịch sử”. Muốn kiểm chứng đầy đủ theo thời điểm cần dữ liệu lưu theo thời gian thực hoặc nguồn vintage được xác minh.
5. Sau khi pipeline ổn định, mở rộng khoảng thời gian và tạo validation/test tách thời gian trước khi kết luận chất lượng dự đoán.

41 test liên quan lịch lịch sử, bổ sung nguồn và runner đều pass. Phase sửa/biến full-live thành xanh không thực hiện vì đây là audit: dữ liệu thiếu và vintage không xác minh không thể khắc phục bằng đổi cờ hoặc tự tạo dữ liệu. Giữ script audit làm vòng kiểm tra lặp lại, không để instrumentation tạm trong pipeline.
