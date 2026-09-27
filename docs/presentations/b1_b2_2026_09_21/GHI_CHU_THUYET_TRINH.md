# Ghi chú thuyết trình — Bộ quy tắc đánh giá B1

10 slide chính: khoảng 7–10 phút. Slide 11–12 là phụ lục.

## Slide 01 — Đánh giá hiệu quả Multi-Agent Crypto

Em trình bày khung đánh giá hệ thống Multi-Agent Crypto: các nhóm metric, quy tắc xử lý tín hiệu, mô phỏng giao dịch và thiết kế so sánh. Mục tiêu là thống nhất cách đo trước khi đánh giá hiệu quả giải pháp.

## Slide 02 — Ba câu hỏi cần trả lời

Hệ thống có ba specialist cho on-chain, thị trường và tâm lý. Validator đo bất đồng và chỉ kích hoạt Debate khi vượt ngưỡng. Mục tiêu đánh giá tách thành dự báo, giao dịch mô phỏng và đóng góp của Debate. Không suy ra lợi nhuận từ accuracy.

## Slide 03 — Bộ metric gồm ba nhóm

Directional accuracy là chỉ số chính của dự đoán. Nhóm tài chính đo hiệu quả giao dịch mô phỏng theo quy tắc cố định. S_final và conflict score giúp giải thích cơ chế, không phải bằng chứng chất lượng tự thân. Tỷ lệ đổi tín hiệu phải đi cùng kết quả sai sang đúng và đúng sang sai.

## Slide 04 — Chấm đúng mẫu số, giữ nguyên ngày lỗi

BUY đúng khi lợi suất tương lai dương, SELL đúng khi âm. Giá không đổi được tính là sai với BUY/SELL. NEUTRAL và lỗi không nằm trong mẫu số directional accuracy. Coverage tính trên toàn bộ ngày yêu cầu, chỉ tính BUY/SELL hợp lệ vào tử số. Tỷ lệ thành công có cả NEUTRAL. Accuracy cặp dùng các ngày hợp lệ chung; metric tài chính phải giữ nguyên lịch, không nối tắt ngày lỗi. Chỉ số không có mẫu số được ghi N/A hoặc null.

## Slide 05 — Quy tắc giao dịch được cố định trước

BUY là long, SELL là short. Một lệnh là chuỗi ngày cùng hướng, số lượng BTC giữ nguyên. NEUTRAL hoặc ngày lỗi đóng lệnh. Quy mô chừa vốn trả phí mở: q bằng E chia P mở nhân một cộng f. Phí trên giá trị mỗi lần giao dịch, đóng cuối kỳ. Short không được nhân dồn một trừ return ngày. Khi cháy vốn, cap equity ở 0, lưu riêng PnL công thức và ghi nhận. Đây là mô phỏng lý tưởng, không phải giao dịch thực tế.

## Slide 06 — Một quyết định, một nhãn sau 24 giờ

Mỗi ngày có một thời điểm quyết định lúc 00:00 UTC. Đầu vào chỉ dùng thông tin đã sẵn có trước thời điểm quyết định; cần xét thời gian công bố, không chỉ ngày ghi trên dữ liệu. P_t là giá đóng cửa ngày trước dùng làm mốc mô phỏng, P_t+24h là giá tại mốc kế tiếp. Lợi suất tương lai chỉ dùng để chấm điểm, không đưa vào đầu vào agent. Cách vào lệnh tại giá mốc là giả định độ trễ bằng không.

## Slide 07 — Chấm hướng và báo độ bao phủ cùng nhau

Directional accuracy bằng số dự đoán đúng chia số ngày hợp lệ có BUY hoặc SELL. BUY đúng nếu lợi suất dương, SELL đúng nếu lợi suất âm; lợi suất bằng không được tính là sai. BUY accuracy và SELL accuracy được báo riêng để phát hiện lệch hướng. Nếu không có dự đoán phù hợp, chỉ số tương ứng là N/A, lưu JSON là null. Luôn báo số đúng, tổng số dự đoán, coverage và tỷ lệ thành công để tránh diễn giải accuracy thiếu mẫu số.

## Slide 08 — Bốn cấu hình để so sánh phương pháp

Bốn cấu hình gồm luôn BUY, luôn SELL, nhánh không Debate và nhánh đầy đủ. Hai nhánh đa agent dùng chung outputs specialist. No-debate vẫn tính conflict nhưng bỏ RCA LLM. Để so chất lượng dự báo theo cặp, dùng các ngày mà hai nhánh có đầu ra hợp lệ và báo riêng chuyển đổi NEUTRAL. Coverage, tỷ lệ thành công và metric tài chính vẫn dùng toàn bộ lịch; không bỏ ngày lỗi rồi nối các ngày còn lại.

## Slide 09 — Tách thay đổi quyết định khỏi cải thiện chất lượng

Tỷ lệ đổi tín hiệu là số ngày tín hiệu sau khác trước Debate chia số ngày có Debate hợp lệ. Nó đo mức độ tác động, chưa chứng minh cải thiện. Trên các cặp BUY/SELL có thể chấm ở cả hai nhánh, báo số sai sang đúng và đúng sang sai. Tách riêng chuyển đổi liên quan NEUTRAL và báo coverage trên toàn bộ lịch. S_final được phân tích theo độ lớn và từng chiều; conflict mô tả mức bất đồng, không thay cho accuracy.

## Slide 10 — Test case kiểm tra cả phép tính và phương pháp

Test phép tính dùng chuỗi giá và tín hiệu nhỏ để tính tay được. Test đánh giá phương pháp dùng dữ liệu thị trường thật và bao phủ tăng, giảm, đi ngang. Hai loại có mục đích khác nhau: ví dụ tính tay kiểm tra công thức, còn dữ liệu lịch sử đánh giá chất lượng dự đoán. Khoảng 90 ngày, cách chia trạng thái thị trường, prompt, ngưỡng và phí phải được chốt trước khi chạy đánh giá.

## Slide 11 — Phụ lục · Ba ví dụ tính tay

Các số liệu ở đây là ví dụ kiểm tra công thức, không phải kết quả hệ thống. Short giữ cố định q ở phí zero có return 5% khi giá từ 100 đến 95, bất kể qua 90. Test phí cần q chừa phí đầu vào. Profit factor phải tổng hợp PnL tiền khi vốn tích lũy, không cộng tỷ lệ phần trăm từng lệnh.

## Slide 12 — Phụ lục · Quy ước báo cáo kết quả

Accuracy cần đi kèm số đúng và mẫu số, coverage và tỷ lệ thành công. Metric tài chính dùng PnL ròng theo tiền sau phí, với drawdown từ đường vốn hằng ngày gồm lãi lỗ chưa thực hiện. Nếu chỉ có lệnh thắng mà không có lệnh lỗ, profit factor hiển thị vô cùng nhưng JSON lưu null kèm lý do. Không có lệnh hoặc toàn hòa vốn thì PF là N/A. Đầu vào, cấu hình và đầu ra từng ngày cần được lưu để đối chiếu kết quả.
