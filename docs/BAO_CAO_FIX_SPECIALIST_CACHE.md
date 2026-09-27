# Sửa kiểm tra nguồn của specialist và lỗi đọc cache

Bản sửa này bổ sung kiểm tra nhận định ban đầu cho Financial, Market, Sentiment và xử lý metadata `service_tier=on_demand` trong phản hồi Groq đã lưu. Đã kiểm tra offline; chưa chạy lại đánh giá bằng API thật sau sửa. Kết quả 5 ngày trước đó được giữ nguyên, không phải kết quả của bản sửa mới.

## 1. Nhận định ban đầu chưa được đối chiếu nguồn

### Nguyên nhân

Prompt đã yêu cầu không bịa dữ liệu, nhưng `validate_specialist_response()` chỉ kiểm tra JSON, signal, confidence và logic_path có nội dung. Vì vậy nhận định “lãi suất thắt chặt hơn” vẫn đi tiếp dù Forecast/Previous của BOC và Fed trong snapshot bằng nhau.

### Thay đổi

Trong `utils/specialist_response.py`:

1. Giữ kiểm tra định dạng; bổ sung lời nhắc rằng Forecast lãi suất bằng Previous không tự chứng minh thắt chặt/tăng lãi suất, tên sự kiện không phải nội dung tuyên bố chính sách.
2. Bắt buộc truyền snapshot gốc vào `request_specialist_response()`. Sau khi JSON hợp lệ, gửi toàn bộ nhận định, gồm signal/confidence, logic_path và các yếu tố giải thích, cùng snapshot đầy đủ cho một lần gọi model `grounding` riêng.
3. Reviewer kiểm tra số liệu, dấu, thời gian, Forecast/Previous/Actual, nhận định không có dữ liệu hỗ trợ và tính nhất quán giữa tín hiệu với giải thích. Cho phép suy luận có điều kiện hợp lý, không yêu cầu nguồn phải viết nguyên văn suy luận. Đây là review nội dung, không bắt specialist chép quote theo schema của Debate.
4. Reviewer trả một quyết định bao phủ toàn bộ candidate: supported/unsupported/contradicted và lý do. Chỉ supported mới được tiếp tục. Kết quả reviewer cũng được kiểm tra schema, không tự coi output lỗi/rỗng là chấp thuận.
5. Khi bị từ chối, gửi lý do để specialist viết lại toàn bộ quyết định một lần trên cùng snapshot. Có thể thay đổi signal/confidence cùng với giải thích; không chỉ sửa câu chữ quanh một tín hiệu cố định.
6. Nếu vẫn không đạt, hoặc reviewer lỗi, phát sinh `GroundingError`; không tự thay bằng NEUTRAL. Tối đa hai lần sinh quyết định và hai lần review, chưa tính retry ở tầng provider.
7. Lưu candidate từng lần, verdict và lý do trong `specialist_grounding`. Không có danh mục đóng giới hạn loại tin tức được dùng.

Trong `agents/financial_agent.py`, `agents/market_agent.py`, `agents/sentiment_agent.py`: truyền snapshot thật vào hàm kiểm tra và lưu audit trong output. Việc dựng belief_vector diễn ra sau khi nhận định được chấp thuận.

Trong `scripts/evaluate_direction.py`: lưu thêm `agent_error_details` cùng audit khi specialist thất bại, để phân biệt lỗi kiểm tra nội dung với lỗi định dạng/provider. Ngày thiếu specialist vẫn không được chấm directional accuracy.

Trong `main.py`: nếu cả ba specialist thất bại và có lỗi grounding, dừng thay vì tự tải nhận định từ `logs.json` cũ để vượt qua bước kiểm tra. Trường hợp một phần specialist thành công vẫn dùng luồng degraded hiện có và báo thiếu agent.

### Giới hạn

Reviewer vẫn là LLM: có thể bỏ sót hoặc từ chối nhầm. Bản sửa thêm cơ chế phát hiện/từ chối và hồ sơ kiểm chứng; không chứng minh đã loại bỏ hoàn toàn hallucination. Không thêm bộ so sánh Forecast/Previous xác định bằng code trong bản này. Khi mỗi specialist thành công lần đầu, cần thêm một lần gọi reviewer, nên ba specialist tăng từ ba lên sáu lần gọi model trước Validator; độ trễ và áp lực rate limit có thể tăng.

## 2. Cache có `service_tier=on_demand`

### Nguyên nhân

Groq trả metadata `on_demand`; schema `ChatCompletion` của SDK đang cài không chấp nhận giá trị này khi gọi `model_validate()` để đọc lại cache. Phản hồi đã nhận thành công vẫn có thể lỗi khi tái sử dụng. Đây không phải lỗi nội dung dự đoán.

### Thay đổi

Thêm `load_cached_completion()` trong `scripts/evaluate_direction.py`:

1. Tạo bản sao dictionary phản hồi để chuẩn bị cho SDK.
2. Chỉ khi `service_tier` bằng `on_demand`, bỏ trường này khỏi bản dùng để parse. Không đổi nó thành `default` hoặc diễn giải sang một tier khác.
3. Vẫn gọi `ChatCompletion.model_validate()` để kiểm tra phần còn lại; dữ liệu nội dung sai schema và giá trị tier lạ khác vẫn báo lỗi.
4. Không sửa file cache gốc, không bỏ qua kiểm tra toàn bộ completion, không thay đổi nội dung model, finish_reason hay usage.

## 3. Kiểm chứng

Lệnh kiểm tra:

```sh
.venv/bin/python -m pytest tests/test_specialist_agents.py tests/test_specialist_grounding.py tests/test_evaluate_direction.py tests/test_grounding.py tests/test_main.py -q
```

Kết quả: **64 test pass** cho các phần liên quan. Các ca mới kiểm tra:

- Forecast/Previous bằng nhau, reviewer từ chối câu thắt chặt, specialist viết lại và chỉ quyết định đã được duyệt mới tạo belief_vector.
- Bị từ chối hai lần thì phát sinh lỗi, không tự sinh NEUTRAL.
- Reviewer thiếu check, thiếu lý do, JSON lỗi hoặc API lỗi không được phê duyệt candidate.
- Toàn bộ yếu tố giải thích và tin ngoài danh mục metric đến reviewer, không cắt còn 200 ký tự.
- Thiếu snapshot bị chặn trước khi gọi LLM.
- Phản hồi `on_demand` tái hiện lỗi cũ nhưng đọc được qua hàm mới, giữ nguyên dữ liệu gốc.
- Tier hợp lệ được giữ; nội dung sai schema vẫn bị từ chối.
- Lỗi grounding không làm main tải lại nhận định cũ khi cả ba agent thất bại.

Các test semantic dùng phản hồi reviewer được kiểm soát: xác minh code thực thi quyết định kiểm tra đúng, không đo độ chính xác của reviewer thật.

Ngoài unit test, đã đọc lại offline **48 phản hồi thật** trong `outputs/direction_smoke_forecast_previous_5d/calls`, trong đó **32 có on_demand**. Tất cả parse thành công; content, finish_reason và usage khớp; không sửa bản ghi gốc. `git diff --check` không phát hiện lỗi whitespace.

Chưa thay công thức KL/variance, Debate, trọng số Mediator hoặc dữ liệu lịch sử. Cần dùng thư mục output mới khi chạy lại vì code/prompt đã đổi; không ghi đè lượt chạy cũ hoặc dùng accuracy cũ để tuyên bố hiệu quả bản sửa.
