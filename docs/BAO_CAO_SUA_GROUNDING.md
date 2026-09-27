# Báo cáo sửa kiểm tra bằng chứng cho Debate và RCA

Ngày kiểm tra: 23/09/2026.

## Mục tiêu và phạm vi

Giảm nhận định không có nguồn hỗ trợ trong Debate/RCA. Tin tức có nguồn vẫn
được sử dụng kể cả khi chủ đề không có trong danh mục chỉ số định lượng.
Giữ công thức phản biện, cập nhật confidence, ngưỡng tín hiệu và Mediator hiện
tại để có thể đánh giá riêng tác động của việc sửa kiểm tra bằng chứng.

## Thay đổi đã thực hiện

1. `utils/grounding.py` tạo danh sách bằng chứng gồm ID, agent sở hữu, ID nguồn
   gốc, metadata và toàn bộ nội dung. Không cắt đoạn theo 200 ký tự.
2. Debate nhận cả nguồn của chính agent và các nguồn khác. Lịch sử lập luận
   không còn cắt 120 ký tự. Ý kiến trong lịch sử không được coi là nguồn độc lập.
3. Đầu ra Debate/RCA gồm 1–3 nhận định (`claims`), phân loại `fact`, `inference`
   hoặc `hypothesis`, kèm `evidence_id` và trích đoạn nguyên văn cho từng nhận định.
4. Code kiểm tra schema, sự tồn tại của ID và việc trích đoạn xuất hiện nguyên
   văn trong nguồn. Một lời gọi LLM riêng kiểm tra nội dung với toàn bộ bằng chứng,
   trả `supported`, `unsupported` hoặc `contradicted` cho từng nhận định.
5. Cho phép tạo lại tối đa một lần khi nội dung bị từ chối. Review lỗi/thiếu kết
   quả không được dùng để chấp nhận nhận định. Log giữ lịch sử thử và lý do.
6. Khi một cập nhật Debate bị từ chối, giữ nguyên signal, confidence,
   belief_vector và logic_path của trạng thái trước vòng đó. Không tự giảm
   confidence vì một phản biện chưa đạt kiểm tra nguồn.
7. RCA không đạt trả thông báo rõ ràng cùng tín hiệu đã quan sát. Kết quả pipeline
   có `rca_grounding`, `debate_status`, `explanations_valid`, và conflict sau Debate.
   Mỗi agent có `debate_audit`, `grounded_claims` nếu được chấp nhận, và nguồn tra cứu.
8. Bộ đánh giá lịch sử lưu validation nhưng loại ngày không đạt kiểm tra lời giải
   thích khỏi tập ngày dự đoán thành công. Ngày đó vẫn nằm trong lịch yêu cầu để
   tính coverage. Run config ghi hash code grounding và cấu hình model kiểm tra.
9. Prompt Financial trong Debate không còn gợi ý rằng MVRV/ETF đã được cung cấp.
   Prompt RCA không ép phải kết luận một nguyên nhân như lệch pha thời gian.
   System prompt specialist nhắc rõ thiếu dữ liệu là chưa biết, phân biệt forecast
   với actual và giả thuyết với sự kiện; specialist ban đầu chưa dùng bộ review
   từng claim như Debate/RCA.

## Kết quả kiểm tra

- 74 test liên quan trực tiếp pass sau thay đổi.
- Toàn bộ **221 test pass**, gồm 19 test mới trong `tests/test_grounding.py`.
- Kiểm tra giữ nguyên dữ liệu sau ký tự thứ 200, nguồn của bản thân/các agent khác,
  metadata, lịch sử sau ký tự thứ 120 và input không bị thay đổi tại chỗ.
- Kiểm tra ID giả, trích đoạn giả, thiếu citation, reviewer bỏ sót hoặc lặp nhận định,
  reviewer lỗi mạng, cập nhật bị từ chối và đánh dấu pipeline không hợp lệ.
- Các ca funding đảo dấu, MVRV/ETF không được nguồn hỗ trợ dùng verdict giả lập
  để xác nhận cơ chế từ chối/retry hoạt động. Đây **không phải** phép đo độ chính xác
  của LLM kiểm tra trên dữ liệu thực tế.
- Ca tin tức ngoài danh mục chỉ số xác nhận code không dùng danh mục để chặn chủ đề.
- Chưa có kết quả chạy lại toàn bộ pipeline với LLM thật cho phiên bản grounding này.

## Giới hạn và chi phí

- Citation khớp chỉ chứng minh trích đoạn tồn tại. LLM reviewer có thể đánh giá sai
  quan hệ giữa nhận định và bằng chứng; cùng model sinh/kiểm tra có thể cùng mắc lỗi.
- Kiểm tra bằng chứng không chứng minh nguồn thật ngoài đời là chính xác, cũng không
  chứng minh dự báo BUY/SELL sẽ đúng. Cần đánh giá riêng với nhãn giá tương lai.
- Mỗi giải thích được chấp nhận ngay cần hai lời gọi LLM: sinh và kiểm tra. Tối đa
  hai lượt sinh và hai lượt kiểm tra nội dung, chưa tính retry lỗi mạng của SDK.
- Ngân sách đầu ra Debate tăng từ 800 lên 1600 token để chứa citations; model
  grounding dùng cấu hình riêng, temperature 0 và max_tokens 1200.
- Giữ toàn bộ nguồn phù hợp với snapshot ngắn hiện tại. Khi thêm nhiều bài báo,
  cần chọn đoạn hoàn chỉnh theo ngân sách context, giữ nguyên nguồn/thời điểm/điều kiện.
- Một agent có thể có vòng chấp nhận rồi vòng bị từ chối: trạng thái giữ ở vòng
  hợp lệ gần nhất và toàn bộ pipeline được đánh dấu partial, không báo Debate thành công đầy đủ.

## Đánh giá công thức phản biện tiếp theo

Công thức hiện tại là heuristic kết hợp cosine trên `direction × strength`,
Jaccard từ vựng và Levenshtein của logic_path. Các phép thử nhỏ cho thấy:

- Cosine một chiều: +0,9 và +0,1 có distance 0; +0,9 và −0,1 có distance 2.
- Jaccard: `funding is positive` / `funding is not positive` có distance 0,25;
  câu đầu / `lãi suất tài trợ lớn hơn không` có distance 1.

Do đó điểm này không nên được diễn giải trực tiếp là chất lượng/sức mạnh phản biện.
Giữ bản hiện tại làm đối chứng; trước khi thay công thức, kiểm tra các cặp cùng nghĩa,
trái nghĩa, khác chủ đề và thiếu bằng chứng. Sau đó so sánh trên cùng snapshot và
đầu ra specialist, giữ cùng cơ chế grounding; đánh giá accuracy kèm coverage, lỗi,
tính bám nguồn, số lời gọi và thời gian. Không chọn công thức bằng kết quả tập test cuối.
