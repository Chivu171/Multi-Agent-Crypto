# Baseline CryptoTrade (EMNLP 2024) — bản viết lại

Viết lại trung thành baseline trong bài:

> Li, Luo, Wang, Chen, Liu, He. *CryptoTrade: A Reflective LLM-based Agent to Guide Zero-shot
> Cryptocurrency Trading*. EMNLP 2024, tr. 1094–1106. Code gốc:
> https://github.com/Xtra-Computing/CryptoTrade (commit `210da73`).

Dữ liệu trong `data/` (giá BTC, thống kê giao dịch on-chain, tin tức đã lọc 01/2023–02/2024) được
chép nguyên từ repo gốc, giấy phép **CC BY-NC-SA 4.0** (`LICENSE`): chỉ dùng phi thương mại, ghi
nguồn, và phần phái sinh dùng cùng giấy phép.

## Thành phần

| File | Nội dung | Tương ứng code gốc |
|---|---|---|
| `env.py` | Môi trường giao dịch: vốn 1.000.000 chia 50/50 tiền/BTC, hành động trong [-1, 1] theo tỷ lệ tiền/coin, chỉ mua/bán (không short), phí 0,4% giá trị + "gas" cố định, chấm giá trị tại giá mở cửa hôm sau | `eth_env.py` |
| `prompts.py` | 4 prompt nguyên văn: on-chain analyst, news analyst, reflection analyst, trader | `env_history.py` |
| `agent.py` | Vòng lặp agent LLM, 6 biến thể ablation, cache từng lời gọi | `eth_trial.py`, `run_agent.py` |
| `rules.py` | Baseline luật: Buy & Hold, SMA(15), SLMA(15/30), MACD, Bollinger(20, 2), Optimal | `run_baseline.py` |
| `run.py` | Chạy từ dòng lệnh | `run_agent.sh` |
| `verify_against_upstream.py` | So sánh trực tiếp với code gốc | — |

Không viết lại LSTM, Informer, AutoFormer, TimesNet, PatchTST: dùng số liệu trong bài (Bảng 2).

## Mức độ trung thành đã kiểm chứng

`verify_against_upstream.py` chạy code gốc và bản này trên cùng dữ liệu:

- 6 chiến lược luật × 3 giai đoạn BTC: lợi suất và Sharpe **trùng tuyệt đối** (sai khác 0).
- 4 prompt × 12 bước với cùng chuỗi hành động: **0 khác biệt** về nội dung (cấu hình `code`); cấu hình `paper` 0 khác biệt sau 25 bước.
- Kết quả luật trùng với **Bảng 2 của bài**:

| Chiến lược | Tăng (01/10–01/12/2023) | Đi ngang (17/06–25/08) | Giảm (12/04–16/06) |
|---|---|---|---|
| Buy & Hold | 39,66% / 0,25 | −0,83% / 0,00 | −15,61% / −0,11 |
| SMA | 22,58% / 0,18 | 3,65% / 0,05 | −21,74% / −0,29 |
| SLMA | 38,53% / 0,25 | −3,14% / −0,05 | −7,68% / −0,09 |
| MACD | 13,57% / 0,15 | −6,71% / −0,09 | −9,51% / −0,09 |
| Bollinger | 2,97% / 0,15 | −3,19% / −0,05 | −1,17% / −0,03 |
| *CryptoTrade (bài báo, GPT-4)* | *26,35% / 0,23* | *−4,07% / −0,04* | *−11,72% / −0,11* |

(lợi suất tổng / Sharpe; Sharpe = trung bình / độ lệch chuẩn lợi suất ngày, lãi phi rủi ro 0.)

### Agent CryptoTrade chạy lại trên model local (29/09/2026)

Cấu hình `paper`, model `google/gemma-4-26b-a4b-qat` (LM Studio, MLX 4-bit, reasoning tắt),
temperature 0. Kết quả trong `outputs/baselines/cryptotrade/<giai đoạn>/agent_paper_*/result.json`.

| Biến thể | Tăng | Đi ngang | Giảm |
|---|---|---|---|
| `full` (Gemma) | **30,47% / 0,23** | −1,63% / −0,01 | **−11,72% / −0,13** |
| `market_only` (Gemma) | −3,31% / −0,07 | 1,76% / 0,03 | −8,49% / −0,10 |
| *Bài báo, GPT-4* | *26,35% / 0,23* | *−4,07% / −0,04* | *−11,72% / −0,11* |

Bản `full` trên Gemma bám sát số của bài báo, nên bản viết lại tái hiện đúng hành vi của phương pháp.
Một giai đoạn khoảng 60–70 ngày mất khoảng 12 phút (`market_only`) và khoảng 50 phút (`full`) trên M1 Pro.

## Những điểm lạ của code gốc — giữ nguyên để so sánh được

1. Prompt ghi "ETH" dù giao dịch BTC.
2. MACD **dưới** đường tín hiệu được coi là tín hiệu **mua** (ngược quy ước thông thường), cả trong
   prompt lẫn baseline MACD.
3. "Gas" dùng hằng số của ETH (0,00147 coin mỗi lệnh) cho cả BTC, tức khoảng 40–55 USD mỗi lệnh.
4. Thứ tự các chỉ số on-chain trong prompt của bản gốc lấy từ `set()`, nên **đổi giữa các lần chạy
   Python**. Bản này dùng thứ tự cố định theo file CSV để tái lập được.
5. `run_baseline.py` gốc không chạy được nguyên trạng (thiếu tham số `dataset`, cố định dữ liệu ETH).
6. Bài có bảng ablation (Bảng 5) nhưng **chỉ cho ETH giai đoạn tăng**. Bản "chỉ thị trường" cho BTC phải
   tự chạy.

## Hai cấu hình (`--profile`)

Code công khai không khớp hoàn toàn với mô tả trong bài, nên có hai cấu hình:

| | `paper` (**mặc định, baseline chính**) | `code` |
|---|---|---|
| Tín hiệu kỹ thuật trong prompt | MA crossover + MACD + Bollinger (mục 2.2, Hình 4) | Chỉ MACD |
| Reflection xem lại | 7 ngày ("previous week", mục 2.4) | 3 ngày |
| Tên tài sản trong prompt | BTC | "ETH" (lỗi của code gốc) |

Bản `paper` không tự chế: hai tín hiệu MA crossover và Bollinger **có sẵn trong `eth_env.py` gốc nhưng bị
comment**. `verify_against_upstream.py` bật lại hai dòng đó cùng reflection 7 ngày rồi so với bản
này: 0 khác biệt sau 25 bước. Chỉ phần câu chữ cố định đổi ETH → BTC; nội dung tin tức và câu trả lời
của model giữ nguyên.

## Biến thể agent (`--variant`)

| Biến thể | Giá | MACD | On-chain | Tin tức | Reflection | Lượt gọi/ngày |
|---|---|---|---|---|---|---|
| `full` | ✓ | ✓ | ✓ | ✓ | ✓ | 4 |
| `market_only` | ✓ | ✓ | | | | 2 |
| `price_only` | ✓ | | | | | 2 |
| `wo_news`, `wo_txnstat`, `wo_reflection` | bỏ từng thành phần | | | | | 3–4 |

`market_only` là baseline "chỉ dữ liệu thị trường" để so với hệ thống 3 agent của đề tài.

## Chạy

```bash
# Baseline luật (miễn phí)
.venv/bin/python -m baselines.cryptotrade.run rules --window bull

# Agent LLM (tốn phí). Mặc định openai/gpt-4o qua OpenRouter, dùng OPENROUTER_API_KEY.
# Đổi bằng CRYPTOTRADE_MODEL / CRYPTOTRADE_BASE_URL / CRYPTOTRADE_API_KEY.
.venv/bin/python -m baselines.cryptotrade.run agent --window bull --variant market_only           # --profile paper (mặc định)
```

Mọi lời gọi LLM được lưu ở `outputs/baselines/cryptotrade/calls/`. Chạy lại cùng lệnh sau khi bị
ngắt sẽ dùng lại các lời gọi đã trả tiền, không tốn thêm. Retry và timeout dùng chính sách chung
của dự án (`utils/llm.py`). Temperature 0 và seed 6216 như bản gốc.

Ngoài metric của bài (lợi suất, Sharpe), `result.json` có thêm `direction_accuracy`: tỷ lệ ngày có
hành động khác 0 mà hướng (mua/bán) trùng hướng giá mở cửa hôm sau, để so với hệ thống của đề tài.

## Chi phí ước tính (GPT-4o)

Tin tức mỗi ngày khoảng 5 bài, mỗi bài tối đa 5.000 ký tự, nên prompt news analyst dài nhất. Một
giai đoạn khoảng 60–70 ngày: `market_only` khoảng 130 lượt gọi, `full` khoảng 260 lượt gọi. Kiểm tra
giá hiện tại của model trước khi chạy.
