# Kết quả so sánh hệ thống với baseline CryptoTrade (EMNLP 2024)

Ngày chạy: 29/09–01/10/2026 · Code: tag `eval-v1` (commit `161da6c`) · Kết quả: commit `e4d33ab`, `31d457e`

## Tóm tắt

- Trên cùng dữ liệu, cùng môi trường giao dịch và cùng model, hệ thống đầy đủ (3 agent + Conflict Analyzer + Debate)
  **hơn baseline "chỉ dữ liệu thị trường"** của CryptoTrade nếu tính trung bình 3 giai đoạn (+0,38% so với −3,35%).
  Lợi thế này đến hoàn toàn từ giai đoạn tăng giá (+16,14% so với −3,31%); ở giai đoạn giảm giá hệ thống thua (−16,63% so với −8,49%).
- Hệ thống **thua CryptoTrade đầy đủ** (trung bình +5,71%) và **thua Buy & Hold** (+7,74%).
- **Debate có ích nhưng nhỏ**: hơn bản không Debate +2,6 điểm (tăng giá), +0,0 (đi ngang), +1,7 (giảm giá), và chưa lần nào làm kết quả xấu đi.
  Cơ chế: Debate chỉ chuyển 11 ngày từ BUY/SELL sang NEUTRAL, chưa bao giờ đổi hướng.
- **Điểm yếu lớn nhất**: tín hiệu không bám theo xu hướng thị trường. Giai đoạn giá tăng 40% hệ thống ra SELL 28 lần, chỉ BUY 19 lần;
  giai đoạn giá giảm lại ra BUY 26 lần, SELL 24 lần. Tỷ lệ đúng hướng của mọi cấu hình nằm trong khoảng 45–63%, gần mức ngẫu nhiên.

## 1. Thiết lập thí nghiệm

| Hạng mục | Giá trị |
|---|---|
| Baseline | CryptoTrade (Li et al., EMNLP 2024), viết lại theo mô tả trong bài (cấu hình `paper`): 3 tín hiệu kỹ thuật, reflection 7 ngày. Đã kiểm chứng khớp code gốc của tác giả và khớp Bảng 2 của bài với các chiến lược luật |
| Dữ liệu | Dữ liệu công khai của CryptoTrade: giá BTC (CoinMarketCap), 6 chỉ số on-chain (Dune), ~5 tin tức/ngày (Google News) |
| Giai đoạn test | Tăng giá 01/10–01/12/2023 (61 ngày giao dịch), đi ngang 17/06–25/08/2023 (69 ngày), giảm giá 12/04–16/06/2023 (65 ngày) |
| Môi trường giao dịch | Của CryptoTrade: 1 triệu USD chia 50/50 tiền/BTC, chỉ mua/bán (không short), phí 0,4% + gas, giao dịch tại giá mở cửa |
| Model (cả hai hệ thống) | `google/gemma-4-26b-a4b-qat` chạy local qua LM Studio (MLX 4-bit, tắt reasoning, temperature 0) |
| Thông tin agent thấy | Quyết định lúc mở cửa ngày D: giá tới D; on-chain và tin tức của D−1. Có test kiểm chứng trùng khớp với thông tin agent CryptoTrade thấy, cả 61 ngày |
| Quy đổi tín hiệu | BUY = mua 50% tiền mặt, SELL = bán 50% BTC, NEUTRAL = giữ (giống cách bài báo quy đổi các baseline luật) |
| Debate bị từ chối một phần | Giữ trạng thái cũ của agent bị từ chối, vẫn giao dịch theo quyết định cuối, gắn cờ (quy tắc Q7) |
| Metric | Lợi suất tổng, Sharpe (trung bình / độ lệch chuẩn lợi suất ngày, đúng công thức của bài), tỷ lệ đúng hướng của các ngày có giao dịch |

Các cấu hình "của mình" (chỉ Market, Market + Financial, Market + Sentiment, không Debate) được tính lại từ cùng một lượt chạy,
bằng cách cho Mediator tổng hợp một phần đầu ra đã lưu, không gọi thêm LLM.

## 2. Kết quả tổng hợp — lợi suất tổng (Sharpe)

| Phương pháp | Tăng giá | Đi ngang | Giảm giá | Trung bình |
|---|---|---|---|---|
| Buy & Hold | +39,66% (0,25) | −0,83% (0,00) | −15,61% (−0,11) | **+7,74%** |
| SLMA (luật) | +38,53% (0,25) | −3,14% (−0,05) | −7,68% (−0,09) | +9,24% |
| Bollinger (luật) | +2,97% (0,15) | −3,19% (−0,05) | **−1,17% (−0,03)** | −0,46% |
| CryptoTrade `full` | +30,47% (0,23) | −1,63% (−0,01) | −11,72% (−0,13) | **+5,71%** |
| CryptoTrade `market_only` | −3,31% (−0,07) | +1,76% (0,03) | −8,49% (−0,10) | **−3,35%** |
| **Của mình: đầy đủ** | +16,14% (0,19) | +1,62% (0,03) | −16,63% (−0,23) | **+0,38%** |
| Của mình: không Debate | +13,53% (0,16) | +1,60% (0,03) | −18,36% (−0,24) | −1,08% |
| Của mình: Market + Sentiment | +12,00% (0,16) | +2,57% (0,04) | −12,55% (−0,17) | +0,67% |
| Của mình: Market + Financial | +2,12% (0,04) | **+6,51% (0,09)** | −18,62% (−0,25) | −3,33% |
| Của mình: chỉ Market | +3,09% (0,06) | +2,61% (0,04) | −10,01% (−0,15) | −1,44% |
| *CryptoTrade trong bài báo (GPT-4)* | *+26,35% (0,23)* | *−4,07% (−0,04)* | *−11,72% (−0,11)* | *+3,52%* |

## 3. Chi tiết từng giai đoạn

### Tăng giá (BTC +39,66%)

| Phương pháp | Lợi suất | Sharpe | Đúng hướng | Ngày giao dịch |
|---|---|---|---|---|
| CryptoTrade `full` | +30,47% | 0,23 | 55,1% | 49 |
| **Của mình: đầy đủ** | +16,14% | 0,19 | 55,3% | 47 |
| Của mình: không Debate | +13,53% | 0,16 | 55,8% | 52 |
| Của mình: Market + Sentiment | +12,00% | 0,16 | 52,9% | 51 |
| Của mình: chỉ Market | +3,09% | 0,06 | 54,5% | 44 |
| Của mình: Market + Financial | +2,12% | 0,04 | 58,3% | 48 |
| CryptoTrade `market_only` | −3,31% | −0,07 | 48,1% | 52 |

Debate ở 36/61 ngày (mâu thuẫn trung bình 0,63 → 0,24 sau Debate); 10 ngày gắn cờ.
Tín hiệu cuối: SELL 28 · NEUTRAL 14 · BUY 19.

### Đi ngang (BTC −0,83%)

| Phương pháp | Lợi suất | Sharpe | Đúng hướng | Ngày giao dịch |
|---|---|---|---|---|
| Của mình: Market + Financial | +6,51% | 0,09 | 63,0% | 54 |
| Của mình: chỉ Market | +2,61% | 0,04 | 54,8% | 42 |
| Của mình: Market + Sentiment | +2,57% | 0,04 | 51,1% | 47 |
| CryptoTrade `market_only` | +1,76% | 0,03 | 45,2% | 62 |
| **Của mình: đầy đủ** | +1,62% | 0,03 | 56,0% | 50 |
| Của mình: không Debate | +1,60% | 0,03 | 54,7% | 53 |
| CryptoTrade `full` | −1,63% | −0,01 | 45,6% | 68 |

Debate ở 32/69 ngày (0,61 → 0,22); 6 ngày gắn cờ. Tín hiệu: BUY 27 · SELL 23 · NEUTRAL 19.

### Giảm giá (BTC −15,61%)

| Phương pháp | Lợi suất | Sharpe | Đúng hướng | Ngày giao dịch |
|---|---|---|---|---|
| CryptoTrade `market_only` | −8,49% | −0,10 | 56,9% | 58 |
| Của mình: chỉ Market | −10,01% | −0,15 | 50,0% | 40 |
| CryptoTrade `full` | −11,72% | −0,13 | 50,0% | 56 |
| Của mình: Market + Sentiment | −12,55% | −0,17 | 49,0% | 51 |
| **Của mình: đầy đủ** | −16,63% | −0,23 | 48,0% | 50 |
| Của mình: không Debate | −18,36% | −0,24 | 45,3% | 53 |
| Của mình: Market + Financial | −18,62% | −0,25 | 45,8% | 48 |

Debate ở 31/65 ngày (0,60 → 0,22); 8 ngày gắn cờ. Tín hiệu: BUY 26 · SELL 24 · NEUTRAL 15.

## 4. Phân tích

**Thêm 2 agent so với chỉ dùng dữ liệu thị trường.** Có ích rõ khi giá tăng: Market một mình +3,09%, đủ 3 agent + Debate +16,14%.
Khi giá giảm thì ngược lại: Market một mình −10,01% là tốt nhất trong các cấu hình của mình, thêm agent làm lỗ nặng hơn.
Nghĩa là các nguồn thêm vào có giá trị, nhưng hệ thống chưa biết khi nào nên tin nguồn nào.

**Từng agent.** Sentiment (tin tức) giúp nhiều nhất khi giá tăng (+9 điểm so với chỉ Market). Financial (on-chain) giúp khi đi ngang
(+3,9 điểm, đúng hướng 63% — cao nhất toàn bảng) nhưng làm tệ hơn khi giá giảm (−8,6 điểm). Kết quả này khớp với phát hiện ở v0
rằng tín hiệu on-chain không ổn định.

**Debate.** Mâu thuẫn giảm mạnh sau Debate (~0,61 → ~0,22) và lợi suất luôn ≥ bản không Debate. Nhưng tác động thực tế nhỏ:
Debate chỉ đổi quyết định ở 11/195 ngày, tất cả đều từ BUY/SELL thành NEUTRAL, vì cơ chế hiện tại chỉ giảm confidence, không cho
agent đổi hướng. Trên các ngày đổi đó, không có ngày nào đổi từ sai thành đúng hoặc đúng thành sai; lợi ích đến từ việc đứng ngoài
những ngày bất định.

**Vì sao thua CryptoTrade đầy đủ.** Tỷ lệ đúng hướng gần như bằng nhau (55,3% so với 55,1% khi giá tăng), nên chất lượng dự đoán
không kém hơn. Khác biệt nằm ở mức vào lệnh: hệ thống của mình mua/bán cố định 50%, còn CryptoTrade tự chọn mức (thường 0,8–1,0
khi tự tin). Trong một giai đoạn tăng mạnh, mua nhiều hơn thì lãi nhiều hơn. Ngoài ra môi trường chỉ cho mua/bán (không short),
nên SELL liên tục khi giá tăng làm hệ thống mất phần lãi.

**Tín hiệu không bám xu hướng.** Hệ thống ra SELL nhiều hơn BUY khi giá tăng và BUY nhiều hơn SELL khi giá giảm. Cùng với tỷ lệ
đúng hướng 45–63%, đây là dấu hiệu các agent đang phản ứng với biến động ngắn hạn (RSI, tin tức trong ngày) hơn là xu hướng.

## 5. Hạn chế

- Mỗi giai đoạn chỉ 61–69 ngày; chênh lệch vài điểm phần trăm chưa có ý nghĩa thống kê.
- Một model local (Gemma 4 26B-A4B); kết quả có thể khác với model lớn hơn. Model này đã được huấn luyện trên dữ liệu năm 2023,
  nên có rủi ro "biết trước" — ảnh hưởng như nhau tới cả hai hệ thống.
- Quy đổi tín hiệu thành ±0,5 là lựa chọn thiết kế; một cách quy đổi khác (theo confidence hoặc S_final) có thể cho kết quả khác.
- Sentiment Agent dùng entropy trung tính 0,5 vì dữ liệu CryptoTrade không có Fear & Greed.
- Các công thức trọng số (entropy, phạt thời gian) và ngưỡng mâu thuẫn 0,4 giữ nguyên như v0, chưa sửa theo các vấn đề đã nêu.

## 6. Câu hỏi đề xuất cho thầy

1. Nên giữ quy đổi cố định ±0,5 (công bằng với baseline luật) hay cho hệ thống chọn mức vào lệnh theo confidence/S_final như
   CryptoTrade?
2. Debate hiện chỉ làm giảm confidence. Có nên cho agent đổi hướng khi có căn cứ (đã có trong lộ trình giai đoạn 2)?
3. Có nên thêm cơ chế nhận biết xu hướng/giai đoạn thị trường để biết khi nào tin nguồn nào, vì giá trị của từng agent thay đổi
   rõ rệt theo giai đoạn?

## 7. Cách chạy lại

```bash
# Baseline luật (miễn phí, vài giây)
.venv/bin/python -m baselines.cryptotrade.run rules --window bull

# CryptoTrade trên model local (LM Studio bật ở cổng 1234)
CRYPTOTRADE_BASE_URL=http://localhost:1234/v1 CRYPTOTRADE_API_KEY=lm-studio \
CRYPTOTRADE_MODEL=google/gemma-4-26b-a4b-qat CRYPTOTRADE_REASONING_EFFORT=none LLM_CALL_TIMEOUT=300 \
  .venv/bin/python -m baselines.cryptotrade.run agent --window bull --variant full

# Hệ thống của mình
LLM_BACKEND=lmstudio LMSTUDIO_MODEL=google/gemma-4-26b-a4b-qat LLM_CALL_TIMEOUT=300 \
  .venv/bin/python -m baselines.cryptotrade.run ours --window bull
```

Thời gian trên MacBook M1 Pro 32 GB: CryptoTrade `market_only` ~12 phút, `full` ~50 phút mỗi giai đoạn; hệ thống của mình
~4,6 giờ mỗi giai đoạn. Số liệu gốc: `outputs/baselines/cryptotrade/<giai đoạn>/*/result.json`.
