# ForexFactory: lịch sự kiện sắp tới và Forecast/Previous

## Bản hiện tại theo yêu cầu mới

**Bộ hiện tại để đánh giá với Forecast/Previous:** `data/datasets/pilot_2022_01_forecast_previous/`.

- Sentiment nhận tên, giờ, đồng tiền, mức ảnh hưởng, **Forecast** và **Previous**, cùng thông tin truy vết nguồn. Chọn tối đa 10 sự kiện High/Medium sắp tới trong tuần UTC, mọi đồng tiền.
- Forecast là kỳ vọng trước công bố; Previous là giá trị kỳ trước. Prompt nói rõ cả hai không phải kết quả thực tế của sự kiện sắp tới.
- Hai trường được giữ nguyên văn từ nguồn, không lấy Actual/Revision bù khi thiếu. Trường null được biểu diễn bằng chuỗi trống; chuỗi trống không được coi là 0.
- **Actual, Revision và cờ kết quả tốt/xấu hơn kỳ vọng vẫn bị loại**. Adapter từ chối nếu có trường này trong sự kiện gửi tới model.
- Giả định minh bạch: dùng Forecast/Previous và lịch trên trang hồi cứu như thông tin đã biết trước mốc dự đoán. Chưa xác minh lịch sử phiên bản hay sửa đổi của các giá trị này, nên không gán `point_in_time_verified=true`.

Đã đối chiếu **226 lượt sự kiện trong 30 snapshot** với nguồn: **180 lượt có Forecast, 185 lượt có Previous**. Đây là lượt xuất hiện trong snapshot; một sự kiện có thể được thấy trước nhiều ngày. 25 snapshot có sự kiện sắp tới, 5 snapshot thứ Bảy có danh sách rỗng theo phạm vi tuần.

**256 test pass**; 8 test mới kiểm tra giữ nguyên Forecast/Previous, không dùng Actual/Revision thay ô trống, chặn trường kết quả bị chèn và chuyển đúng dữ liệu tới Sentiment. Dựng lại offline giống hệt từng byte; nhãn giữ nguyên. Chưa chạy lại LLM.

File xem nhanh: `forex_schedule.jsonl`. Toàn bộ đầu vào: `snapshots.jsonl`. `features.csv` bổ sung số Forecast/Previous không trống trong danh sách sự kiện được chọn. `verification_result.json` lưu kết quả đối chiếu thực tế.

```sh
# Dựng lại từ các raw response đã lưu
.venv/bin/python -m scripts.enrich_historical_dataset \
  --output data/datasets/pilot_2022_01_forecast_previous --offline --calendar-values

# Khi chủ động chạy đánh giá LLM, chọn đúng bộ mới (lệnh này có gọi provider)
.venv/bin/python -m scripts.evaluate_direction \
  --dataset data/datasets/pilot_2022_01_forecast_previous \
  --output outputs/direction_forecast_previous
```

Không bật `--require-full-live` cho bản dựng theo giả định này. Nó vẫn còn thiếu global ratio ở 19 ngày, khác chu kỳ ratio của live và chưa có vintage được xác minh. Chế độ lịch cũ vẫn được hỗ trợ; các bộ cũ không bị ghi đè. Để so Debate, tất cả nhánh phải dùng cùng bộ dữ liệu mới và cùng đầu ra Specialist.

## Bản lịch thuần trước đó, giữ lại để đối chiếu

Theo phạm vi người dùng làm rõ, hệ thống cần biết **sắp có sự kiện gì**, không cần biết trước kết quả kinh tế công bố. Đã bổ sung chế độ lịch sự kiện vào bộ mới `data/datasets/pilot_2022_01_calendar/` và adapter Sentiment. Hai bộ pilot gốc và enriched trước đó được giữ nguyên.

## Đầu vào

- Tên sự kiện, thời gian diễn ra, đồng tiền và mức ảnh hưởng.
- Kèm ID, URL và file nguồn để đối chiếu.
- Không đưa Actual, Forecast, Previous, Revision hoặc cờ kết quả tốt/xấu hơn kỳ vọng vào sự kiện gửi cho model.
- Giả định được ghi rõ: lịch lịch sử phản ánh lịch đã thông báo trước thời điểm dự đoán; chưa kiểm chứng các lần dời giờ/đổi tên/đổi mức ảnh hưởng. Không gán lịch này là vintage đã xác minh.

Trong mỗi snapshot, chọn tối đa 10 sự kiện High/Medium sắp tới của mọi đồng tiền trong tuần UTC hiện tại (Chủ nhật–thứ Bảy), sắp xếp theo thời gian. Không đưa sự kiện đã qua vào danh sách sắp tới; loại sự kiện có thời gian masked/tentative để không tạo giờ chính xác giả. Đây là quy tắc dựng lịch được ghi minh bạch, không khẳng định khớp tuyệt đối với múi giờ/tuần của feed live.

## Kết quả

- **30/30 snapshot có nguồn lịch.**
- **25 ngày có sự kiện sắp tới được chọn; 5 ngày thứ Bảy có danh sách rỗng** theo quy tắc tuần hiện tại. Lịch rỗng khác với nguồn lịch thiếu.
- 226 lượt sự kiện xuất hiện trong các snapshot đã được đối chiếu với bản ghi gốc. Một sự kiện có thể xuất hiện trước nhiều ngày; đây không phải 226 tin độc lập.
- 99 ID sự kiện khác nhau: gồm cả các sự kiện sau ngày cuối pilot, vì snapshot ngày 30/01 có thể thấy lịch tuần sắp tới. Số này không cùng phạm vi với 95 sự kiện High/Medium diễn ra trong riêng 01–30/01.
- Không có trường kết quả kinh tế trong các sự kiện đưa vào model.
- Funding vẫn đủ 30 ngày; global ratio 5 phút vẫn chỉ đủ 11 ngày. Các giới hạn nguồn khác không tự biến mất khi có lịch.

## File nên xem

- `forex_schedule.jsonl`: chỉ phần lịch sạch theo từng ngày, dễ kiểm tra.
- `snapshots.jsonl`: toàn bộ đầu vào cho hệ thống, gồm lịch và các nguồn khác.
- `features.csv`: thêm cờ có lịch, số sự kiện được chọn và số sự kiện trong 24 giờ trong danh sách được chọn. Tên/nội dung sự kiện nằm trong JSONL.
- `verification_result.json`: kiểm tra 30 snapshot, từng sự kiện, trường bị loại và dựng lại offline.
- `forex_events_RETROSPECTIVE_ONLY.json`: dữ liệu hồi cứu đầy đủ, vẫn không đưa trực tiếp vào prompt.

## Code và kiểm tra

`utils/historical_calendar.py` dựng lịch bằng whitelist trường; adapter kiểm tra lại để từ chối sự kiện bị chèn trường Actual/Forecast/Previous/Revision hoặc sự kiện đã qua. Prompt chỉ cho phép bàn về bất định trước sự kiện, không được bịa kết quả hoặc bất ngờ kinh tế.

12 test mới về bỏ trường kinh tế, tính bất biến khi sửa kết quả công bố, lịch rỗng/thiếu nguồn, giờ không chắc chắn, mọi đồng tiền, sắp xếp/giới hạn, chặn giá trị bị chèn và adapter Sentiment. Toàn bộ suite: **248 test pass**. Dựng lại offline cho artifact giống hệt từng byte. Chưa chạy một đợt LLM đánh giá mới.

```sh
.venv/bin/python -m scripts.enrich_historical_dataset \
  --output data/datasets/pilot_2022_01_calendar --offline --calendar-schedule
```

Khi đánh giá, truyền bộ `pilot_2022_01_calendar` cho `--dataset`; không mặc định rằng chương trình đã đổi từ bộ pilot cũ. Muốn so các nhánh Debate phải dùng cùng bộ này và cùng đầu ra Specialist. `--require-full-live` vẫn từ chối vì đây là bản dựng theo giả định và còn thiếu ratio, không phải snapshot đầy đủ đã xác minh của live.
