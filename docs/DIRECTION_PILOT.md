# Chạy thử tỷ lệ dự đoán đúng hướng 24 giờ

```bash
python -m scripts.evaluate_direction --output outputs/direction_run_new
```

Script thực sự gọi LLM theo model/key trong cấu hình hiện tại. Mỗi ngày gọi Financial, Market, Sentiment (ba request độc lập), rồi dùng Validator, conditional Debate và Mediator của project. Lượt gọi LLM có thể phát sinh chi phí theo tài khoản/provider.

## Đầu vào và khác biệt với live

- Chỉ đọc `snapshots.jsonl` trước dự đoán; kiểm tra checksum trong manifest.
- Ba specialist hỗ trợ `run(data=..., reference_time=...)`; mặc định `run()` vẫn dùng fetcher live như trước.
- Prompt gốc được giữ, thêm yêu cầu dự báo 24 giờ và chỉ dùng bằng chứng trước cutoff.
- Market tính lại EMA/RSI từ 60 nến cuối, khớp cửa sổ live hiện tại (dataset features dùng cửa sổ 90 nến).
- Chỉ có OHLCV, bốn chỉ số on-chain và F&G. ForexFactory, funding, long/short được đánh dấu unavailable, không bịa bằng 0.
- Metadata thời gian của on-chain/F&G dùng thời điểm quan sát nguồn; Market dùng mốc nến đã đóng. Mediator nhận `current_time=prediction_time`, không lấy thời gian năm 2026 để phạt dữ liệu năm 2022.
- Giữ ngưỡng signal ±0.05, conflict 0.4 và tham số Debate hiện có. Không tune theo kết quả pilot.
- Script không gọi `main.py`, không dùng fallback `outputs/logs.json` và không gọi lại nguồn giá hiện tại.

## Chấm điểm

Sau vòng dự đoán mới mở `labels.csv`. Ghép bằng `sample_id` và dùng `return_24h`, không dùng nhãn ba lớp ±1% để chấm hướng:

- BUY đúng khi `return_24h > 0`.
- SELL đúng khi `return_24h < 0`.
- Giá đứng yên: BUY/SELL đều không đúng.
- NEUTRAL loại khỏi mẫu số directional win rate, báo riêng số lượng và coverage.
- Ngày thiếu specialist hoặc lỗi LLM trong validator/debate: không chấm như dự đoán bình thường.
- Không có dự đoán BUY/SELL hợp lệ: win rate = `null` (chưa tính được), không phải 0%.

Báo cáo thêm BUY/SELL accuracy, coverage trên toàn bộ ngày yêu cầu và coverage trên các ngày chạy thành công. Không tự bỏ ngày lỗi khỏi số ngày yêu cầu.

## Output

- `run_config.json`: cấu hình model không chứa key, hash snapshot/code và giới hạn.
- `calls/*.json`: prompt thực tế, phản hồi LLM, usage nếu provider trả về, lỗi HTTP và thời gian chạy. Không lưu API key.
- `days/<ngày>.json`: đầu ra specialist, validation/debate, mediator và trạng thái; không có ground truth.
- `predictions.csv`: kết quả đã ghép lợi suất thực tế để chấm.
- `summary.json`, `REPORT.md`: tỷ lệ đúng hướng và coverage.

Lỗi 429 được chờ 20 rồi 40 giây trước khi thử lại (tối đa ba request). Hai ngày lỗi liên tiếp khiến phần còn lại được ghi `not_run_provider_failures`, tránh gửi hàng loạt request khi provider không đáp ứng.

Có thể tái sử dụng phản hồi thành công từ lượt trước:

```bash
python -m scripts.evaluate_direction --output outputs/direction_retry_new --reuse-calls-from outputs/direction_pilot/calls
```

Chỉ tái sử dụng khi tên file hash khớp endpoint, model và toàn bộ tham số request/prompt. File ngày đã hoàn thành được giữ khi chạy lại cùng output; để thử lại ngày lỗi dùng output mới và reuse các call thành công. Không thay model tự động khi bị giới hạn tốc độ.

## Diễn giải kết quả

Đây là thử nghiệm trên 30 ngày thuộc train và nguồn dữ liệu rút gọn; chưa phải kết quả test độc lập của hệ thống đầy đủ. Kiến thức lịch sử trong mô hình LLM có thể ảnh hưởng kết quả. Publication-time của on-chain/F&G vẫn dựa trên giả định của dataset. Win rate trên ít ngày chạy được không đại diện cho toàn bộ 30 ngày.
