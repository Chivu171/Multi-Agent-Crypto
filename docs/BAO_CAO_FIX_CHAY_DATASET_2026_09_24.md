# Kiểm tra, sửa đường chạy dataset và chạy lại 5 ngày

## Phạm vi và kết quả

Theo yêu cầu, bỏ qua việc đồng bộ EMA với ML; tập trung hệ thống multi-agent hiện tại. Không sửa dữ liệu/nhãn trong `data/datasets/pilot_2022_01_forecast_previous`, không điền số giả cho chỗ thiếu. Chạy lại đúng 12, 19, 20, 22, 26/01/2022 bằng API thật.

Lượt cuối: `outputs/direction_fixed_inputs_no_reasoning_5d/`. Đã thử đủ 5 ngày; 4 ngày hợp lệ, 1 ngày bị specialist reviewer từ chối sau lần viết lại. Không còn bản ghi lỗi provider cuối cùng hoặc phản hồi bị cắt trong lượt này. Có 429 tạm thời đã retry thành công; không kết luận dịch vụ sẽ luôn khả dụng.

| Ngày | Kết quả | Giá sau 24h | Chấm hướng |
| --- | --- | ---: | --- |
| 12/01 | Lỗi grounding Sentiment | +2,7461% | Không chấm |
| 19/01 | NEUTRAL | −1,6342% | Không chấm |
| 20/01 | SELL | −2,3502% | Đúng |
| 22/01 | BUY | −3,7697% | Sai |
| 26/01 | NEUTRAL | −0,4031% | Không chấm |

- Tỷ lệ chạy thành công: 4/5 = 80%.
- Coverage BUY/SELL: 2/5 = 40%.
- Directional accuracy: 1/2 = 50%; SELL 1/1, BUY 0/1.
- Luôn SELL trên đúng hai ngày được chấm: 2/2. Chưa vượt baseline; mẫu quá nhỏ để kết luận hiệu quả.
- Không tính tài chính từ các ngày rời nhau. Các ngày đã được xem ở những lượt trước, không phải held-out test.

## Chẩn đoán theo diagnosing-bugs

Đã áp dụng vòng tái hiện → giả thuyết → thay một yếu tố → test hồi quy → chạy thật. Không có CONTEXT.md/ADR trong danh sách file repository. Các giả thuyết đã phân biệt: dữ liệu đầu vào sai; quote bị model chép sai; model không khả dụng/quota; ngân sách suy luận làm JSON bị cắt.

### 1. Dataset hiện có qua kiểm tra, nhưng adapter thiếu chặn dữ liệu hỏng

Kiểm tra 30 snapshot, giá/nhãn với Binance gốc đã lưu, checksum và thời gian theo giả định recorded availability đều đạt. Khi cố tình sửa một bản sao snapshot, adapter cũ vẫn nhận cả 5 lỗi sau:

- available_at on-chain sau thời điểm dự báo;
- phần trăm thay đổi là NaN;
- giá đóng cửa âm;
- nến chưa đóng tại mốc dự báo;
- feature close khác giá nến cuối.

Lệnh tái hiện trước sửa:

```sh
.venv/bin/python -m pytest tests/test_snapshot_input_boundary.py -q
# 5 failed — DID NOT RAISE ValueError
```

Đã thêm `validate_snapshot_input()` trước adapter: kiểm tra UTC midnight/horizon 24h; tối thiểu 60 nến đóng, liên tục và có ngày cuối; giá hữu hạn/dương, volume không âm, OHLC hợp lệ; feature close/volume khớp nến; nguồn on-chain/Fear & Greed có timestamp hợp lệ và giá trị hữu hạn. Thiếu nguồn bắt buộc thì báo lỗi trước gọi model.

Sau sửa 5 test trên pass và 30 snapshot thật vẫn qua. Đây là sửa lỗ hổng kiểm tra ở code, không phải phát hiện cả 5 kiểu lỗi trong dataset thực tế. Ratio thiếu vẫn là null; không buộc mọi nguồn tùy chọn phải có để chạy bản pilot.

### 2. Lỗi quote nguyên văn ở RCA/Debate

Tái hiện từ log cũ: `Quote does not occur verbatim in E001`. Model có thể làm tròn số trong quote, ví dụ nguồn có 0.709219... còn quote ghi 0.71. Đoạn quote sai phải tiếp tục bị từ chối; không nới quy tắc so khớp để nhận nó.

Sửa `utils/grounding.py`:

- Cấp `quote_ids` L1/L2… theo các dòng nguồn thật.
- Model trả evidence_id và quote_id; code tự lấy dòng nguồn nguyên văn để điền quote.
- Mã nguồn/mã dòng sai, hoặc quote đi kèm trái với dòng đã chọn, vẫn bị từ chối.
- Tiếp tục chạy semantic reviewer với claims và nguồn đầy đủ. Legacy quote nguyên văn vẫn được kiểm tra như trước.
- Cập nhật prompt RCA/Debate để dùng schema mới, giữ nguyên công thức conflict và cập nhật confidence.

Test được viết trước sửa: ca tham chiếu nguồn mới thất bại, sau sửa đạt; ca trích sai vẫn thất bại đúng quy tắc. Đã replay riêng RCA bằng đầu ra specialist thật ngày 19/01 lưu từ lượt trước, gọi model thật: accepted ngay lần đầu. File `RCA_REPLAY.json` là kiểm tra riêng bước RCA, không phải prediction bổ sung và không nhập vào accuracy 5 ngày. Lượt cuối 5 ngày không kích hoạt Debate, nên chưa chứng minh chất lượng toàn bộ hai vòng Debate bằng lượt này.

### 3. Model 404/429

Market cũ `inclusionai/ling-3.0-flash-vl:free` trả 404; reviewer Qwen free gặp 429. Đã kiểm tra danh mục OpenRouter và gọi thử model thay thế bằng yêu cầu JSON thật, không chọn bản trả phí.

Cấu hình được ghi trong `.env` và run_config.json:

| Vai trò | Model |
| --- | --- |
| Financial, Market | inclusionai/ling-3.0-flash-fin:free |
| Sentiment | cohere/north-mini-code:free |
| Validator/RCA, grounding reviewer | inclusionai/ling-3.0-flash-sante:free |
| Debate | dots-studio/dots-3-note-preview:free |

Các vai trò vẫn dùng prompt riêng dù chia sẻ model. Không diễn giải thay đổi accuracy giữa các lượt như tác động thuần túy của code, vì model/cấu hình cũng thay đổi. `.env.example` được cập nhật, không ghi khóa bí mật vào báo cáo.

### 4. JSON bị cắt vì ngân sách reasoning

Lượt `direction_fixed_inputs_5d` sau sửa input/quote vẫn thất bại 5/5, chủ yếu do reviewer hết ngân sách trước khi có JSON hoàn chỉnh. Log ghi `finish_reason=length`, content rỗng; usage cho thấy phần lớn completion budget dùng cho reasoning. Tăng giới hạn một yêu cầu lên 4096 vẫn bị cắt. Với cùng yêu cầu, cấu hình reasoning effort none trả JSON hoàn chỉnh.

Điều này phù hợp với [tài liệu OpenRouter về reasoning và max_tokens](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens): ngân sách có thể bao gồm cả suy luận và nội dung trả về. Catalog tại thời điểm kiểm tra cho biết bốn model ID được chọn không bắt buộc bật reasoning. Không giả định model khác cũng hỗ trợ tắt.

Sửa `utils/config.py` và `utils/llm.py`: thêm tùy chọn `OPENROUTER_REASONING_EFFORT`, gửi qua extra_body.reasoning.effort cho OpenRouter, ghi vào cấu hình thí nghiệm. Đặt none cho bộ model đã kiểm tra; giữ nguyên giới hạn max_tokens. Không lấy nội dung suy luận nội bộ để sửa JSON, không bỏ qua finish_reason=length. Test mô phỏng provider dùng hết ngân sách khi thiếu tùy chọn đã đỏ trước sửa và xanh sau sửa.

Lượt cuối có 34 phản hồi provider đã lưu, 0 phản hồi bị cắt và 0 bản ghi provider error cuối cùng; 75.251 total usage tokens được trả trong các bản ghi này. Không bao gồm mọi retry HTTP hoặc các probe riêng.

## Vấn đề còn lại

Sentiment 12/01 ban đầu tự thêm “bán tháo trái phiếu”; lần sửa còn thêm “lãi suất trái phiếu tăng do đấu giá”, trong khi snapshot chỉ có lịch đấu giá và previous. Reviewer từ chối, nên ngày này được ghi error đúng quy tắc, không chuyển thành NEUTRAL hoặc tính là dự đoán hợp lệ.

Reviewer cũng không hoàn hảo. Ví dụ lý do từ chối có chỗ đánh đồng “PPI m/m tăng 0,4%” với “forecast tăng so với previous”; tỷ lệ dương có thể thấp hơn kỳ trước. Lần từ chối này còn những nhận định khác thiếu căn cứ, nhưng không coi tất cả lý do reviewer đưa ra là đúng. Không nới kiểm tra để ép đạt 5/5; cần đánh giá riêng chất lượng generator/reviewer.

Dataset vẫn có 19 ngày thiếu ratio, Forex chưa xác minh vintage và các giả định thời điểm công bố. Những hạn chế này được giữ nguyên và công khai; không thể sửa bằng đổi cờ eligible_full_live hoặc tạo số liệu.

## Kiểm tra cuối

```sh
.venv/bin/python -m pytest tests/test_snapshot_input_boundary.py tests/test_grounding.py tests/test_historical_calendar.py tests/test_historical_enrichment.py tests/test_evaluate_direction.py tests/test_specialist_agents.py tests/test_specialist_grounding.py tests/test_main.py tests/test_llm.py -q
# 111 passed

.venv/bin/python -m scripts.audit_dataset_compatibility --output outputs/dataset_compatibility_2026_09_24/audit.json
# 30/30 adapter; 30 labels match archived Binance
```

Hash dataset và code ghi lúc bắt đầu lượt cuối vẫn khớp khi hoàn tất. Đối chiếu lại lợi suất 5 ngày khớp giá gốc trong labels. `git diff --check` đạt; không để debug instrumentation tạm trong pipeline. Các probe/audit được giữ trong thư mục output có tên rõ ràng để kiểm chứng.
