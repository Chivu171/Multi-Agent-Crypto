# Đăng ký trước: kiểm chứng trên ETH năm 2023

Viết ngày 18/10/2026, **trước khi tải dữ liệu ETH** về repo và trước khi chạy bất kỳ hệ thống nào trên ETH.
Mọi cấu hình dưới đây cố định từ các thí nghiệm trên BTC; không chỉnh tham số nào trên ETH. Mọi kết quả sẽ
được báo cáo, kể cả khi giả thuyết không đúng.

## Dữ liệu

Bộ dữ liệu ETH của CryptoTrade (repo gốc Xtra-Computing/CryptoTrade, nhánh `master`, giấy phép CC BY-NC-SA 4.0):
`eth_daily.csv` (giá), `eth_more_transaction_statistics.csv` (on-chain), `gnews/` (tin tức). Đọc theo đúng
`get_paths('eth')` của `eth_env.py` gốc.

Sáu khung, cùng ngày với BTC:

| Khung | Ngày |
|---|---|
| dev_feb_apr | 2023-02-20 → 2023-04-11 |
| bear (test) | 2023-04-12 → 2023-06-16 |
| sideways (test) | 2023-06-17 → 2023-08-25 |
| dev_aug_sep | 2023-08-26 → 2023-09-30 |
| bull (test) | 2023-10-01 → 2023-12-01 |
| dev_dec_jan | 2023-12-02 → 2024-01-31 |

Trên ETH không có bước chọn tham số nào, nên cả sáu khung được dùng như dữ liệu kiểm chứng; tên dev/test chỉ để
so sánh với BTC.

## Hệ thống

- **Hệ thống đề xuất**: đúng mã eval-v1 (ngưỡng mâu thuẫn 0,4, tranh biện 2 vòng không đổi hướng, Mediator,
  ánh xạ ±0,5), model `google/gemma-4-26b-a4b-qat`. Chỉ đổi tên tài sản trong câu chữ (BTC → ETH, Bitcoin →
  Ethereum). **Giữ nguyên nhãn chỉ báo của CryptoTrade** (kể cả nhãn đảo chiều) để kiểm chứng đúng hệ thống đã
  phân tích.
- **CryptoTrade đầy đủ**: cấu hình `paper`, tên tài sản ETH, cùng model.
- **Chiến lược luật**: Buy & Hold, SMA, SLMA, MACD, Bollinger, so với Bảng 2 của bài báo gốc nếu có.

## Giả thuyết chính (H1)

Trọng tài theo độ tin cậy, **cấu hình cố định**:
- ngày mâu thuẫn = có ít nhất một đóng góp Mediator dương và một âm;
- bỏ phiếu theo Σ dᵢ·(rᵢ − 0,5), rᵢ = (số lần đúng + 5) / (số lần có hướng + 10) trong các ngày mâu thuẫn
  **trước đó**, cộng dồn qua cả sáu khung theo thứ tự thời gian; kết quả một ngày được biết ở giá mở cửa hôm sau;
- ngày không mâu thuẫn giữ quyết định của eval-v1; quy đổi ±0,5.

**H1**: trên ETH, gộp sáu khung, tỷ lệ đúng hướng trên mọi ngày giao dịch của trọng tài cao hơn eval-v1.

Kiểm định: hiệu tỷ lệ đúng (trọng tài − eval-v1), khoảng tin cậy 95% bằng bootstrap theo khối 5 ngày trên các
ngày (10.000 lần, seed 0). H1 được ủng hộ nếu cận dưới của khoảng tin cậy lớn hơn 0. Báo cáo kèm lợi suất (dự
kiến không tăng, vì trên BTC trọng tài làm lợi suất giảm).

## Các kết quả phụ (mô tả, không chọn tham số)

1. Lợi suất của hệ thống đề xuất so với CryptoTrade đầy đủ và Buy & Hold (dev, test, gộp), bootstrap như trên BTC.
2. Tỷ lệ đúng hướng của từng agent ở tầm 1, 3, 7 ngày so với mức ngẫu nhiên cùng tỷ lệ BUY.
3. Tỷ lệ BUY của CryptoTrade đầy đủ.
4. Luật "không bao giờ SELL" (đã chọn trên dev BTC) so với CryptoTrade.
5. Phép xáo trộn thứ tự lệnh.
6. Tỷ lệ Market Agent nói SELL khi giá nằm trên cả EMA20 và EMA50.
7. Bảng phân xử ở các ngày mâu thuẫn (Bảng tab:conflict-rules của báo cáo).
