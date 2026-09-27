# Đánh giá v0 — cấu hình đóng băng

Đóng băng ngày 27/09/2026 tại commit `97ec1db`, tag git `eval-v0`. Trong suốt đợt chạy không được
sửa các file có hash trong `run_config.json` (`code_sha256`); nếu sửa, `evaluate_direction` sẽ từ
chối chạy tiếp vào thư mục này.

## Dữ liệu
- Dataset: `data/datasets/pilot_2022_01_forecast_previous`, 30 ngày 01–30/01/2022
  (sha256 snapshots `fb73e9acc0ca73d8…`, nhãn kiểm tra theo `dataset_manifest.json`).
- Mỗi ngày: một quyết định lúc 00:00 UTC, chân trời 24 giờ.

## Model (OpenRouter, bản miễn phí, reasoning = none)
| Vai trò | Model | Temperature | Max tokens |
|---|---|---|---|
| Financial | inclusionai/ling-3.0-flash-fin:free | 0.1 | 1500 |
| Market | inclusionai/ling-3.0-flash-fin:free | 0.2 | 1500 |
| Sentiment | cohere/north-mini-code:free | 0.4 | 1800 |
| Validator (RCA) | inclusionai/ling-3.0-flash-sante:free | 0.0 | 1500 |
| Debate | dots-studio/dots-3-note-preview:free | 0.3 | 1600 |
| Reviewer | inclusionai/ling-3.0-flash-sante:free | 0.0 | 1200 |

## Ngưỡng và tham số (utils/thresholds.py)
- Conflict = 0.6·KL + 0.4·Variance; kích hoạt RCA/Debate khi ≥ 0.4.
- Debate 2 vòng, hệ số giảm confidence 0.35.
- |S_final| ≤ 0.05 → NEUTRAL.
- Giới hạn 5 phút/ngày; tối đa 3 lần gọi mỗi request, 60 giây/lần.

## Đánh giá (theo B1)
- 4 cấu hình: luôn BUY, luôn SELL, không Debate, đầy đủ. Nhánh không Debate tính lại bằng
  Mediator trên đầu ra specialist; vẫn hợp lệ khi chỉ RCA/Debate bị từ chối.
- Phí mỗi chiều: 0% / 0,1% (cơ sở) / 0,2%.
- 10 ngày (02, 06, 12, 13, 15, 19, 20, 21, 22, 26) dùng lại phản hồi LLM đã lưu từ
  `direction_resilience_5d` và `direction_debate_5d` (cùng code, cùng prompt).

## Lệnh
```
.venv/bin/python -m scripts.evaluate_direction --dataset data/datasets/pilot_2022_01_forecast_previous \
  --output outputs/eval_v0_30d \
  --reuse-calls-from outputs/direction_resilience_5d/calls outputs/direction_debate_5d/calls
.venv/bin/python -m scripts.report_evaluation --run outputs/eval_v0_30d
```

## Giới hạn
Đánh giá sơ bộ: không phải tập kiểm tra độc lập; chỉ giai đoạn BTC giảm; mẫu nhỏ; model có thể
đã biết giá 2022; mô phỏng giao dịch lý tưởng (không trượt giá, funding, chi phí vay short).
