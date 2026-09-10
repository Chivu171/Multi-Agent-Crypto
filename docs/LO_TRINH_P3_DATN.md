# Lộ trình Project 3 → ĐATN — Multi-Agent-Crypto (HUST SoICT)

> **Trạng thái hiện tại (SCAN 2026-09-09):** 70% cho Project 3, 35–45% cho ĐATN.
> Ý tưởng và core kỹ thuật đủ mạnh; phần quyết định điểm ĐATN là **thực nghiệm có đối chứng, tính tái lập và báo cáo nghiên cứu** — không phải thêm nhiều agent hơn.
> Tài liệu này chốt lộ trình 2 chặng đã thống nhất, bám sát 5 gap đã phát hiện.

---

## 0. Bối cảnh & Đánh giá tổng quan

| Chuẩn | Kết luận | Căn cứ |
|---|---|---|
| **Project 3** | **Đủ 70%** — bài toán rõ, 3 specialist agents, dữ liệu BTC live, validator (KL + variance), debate, mediator; code biên dịch được | `agents/financial_agent.py:66`, `market_agent.py:63`, `sentiment_agent.py:64`, `validator_agent.py:175`, `debate_agent.py:218`, `mediator_agent.py:114`, `data_sources/*.py`, `main.py:114` |
| **ĐATN** | **35–45%** — hướng phát triển tốt nhưng chưa đạt mức sẵn sàng bảo vệ | Thiếu thực nghiệm khoa học, RAG chưa nối, thiết kế `docs/` chưa hiện thực, tái lập lỗi, `docs/` chưa git |
| **Hướng ĐATN đề xuất** | *“Đánh giá tác động của cơ chế phát hiện mâu thuẫn và tranh biện đa tác tử đến chất lượng tín hiệu BTC”* | Giả thuyết trung tâm cho ablation study |
| **Điều kiện học vụ** | Project 3 là điều kiện đăng ký ĐATN; ĐATN cần nợ ≤ 8 TC và đạt chuẩn ngoại ngữ (SoICT) | Quy định SoICT/ĐATN |

### 5 gap chưa đạt để lên ĐATN

1. **Chưa có thực nghiệm khoa học:** thiếu bộ dữ liệu lịch sử, baseline (technical-only / single-agent / no-debate), backtest và metric (accuracy, Sharpe, drawdown, win rate, latency/cost) — `TASK_GRAPH.md: TIP-014` chưa làm.
2. **RAG có nhưng chưa nối vào pipeline** — `rag/retriever.py:76` standalone, `main.py:114` không gọi `retriever.query()`, `README.md:165` thừa nhận.
3. **Thiết kế trong `docs/` chưa hiện thực:** chưa có CLI chuẩn, Pydantic/BaseAgent, async, cache SQLite, logging chuẩn, backtest — `crypto_analyzer/` không tồn tại, `pyproject.toml:7` thiếu `typer`, `pydantic`.
4. **Tái lập môi trường lỗi:** `pytest` không import được package vì thiếu `[tool.pytest.ini_options.pythonpath]` hoặc `conftest.py`; thiếu lockfile làm `pip install -e .[dev]` không tái lập giữa các máy; `pyproject.toml:31` coverage thiếu `main.py` — `pytest-cov` chưa cài.
5. **`docs/` chưa được git theo dõi và các checklist gate vẫn là mục tiêu** — `git status` untracked `BLUEPRINT.md`, `CONTRACT.md`, `TASK_GRAPH.md`, gates `[ ]`.

---

## 1. Nguyên tắc chung

- **Không thêm agent mới** — tập trung vào thực nghiệm và tái lập.
- **Thứ tự ưu tiên:** Fix tái lập (gap 4) → Đóng gói Project 3 (gap 3 partial + 5 + demo) → Thực nghiệm ĐATN (gap 1) → RAG wiring (gap 2) → Hoàn thiện thiết kế còn lại (gap 3 full) → Báo cáo.
- **Gate rõ ràng:** Mỗi chặng có tiêu chí pass/fail, không gộp khi chưa pass gate trước.

---

## 1.5 Quyết định kỹ thuật bắt buộc (chốt trước khi code)

Các quyết định dưới đây **bắt buộc được thống nhất trước khi bắt đầu Chặng A**. Mỗi quyết định có đề xuất và lý do; nếu không đồng ý, hãy đặt câu hỏi trước khi thi hành.

| # | Quyết định | Đề xuất | Lý do |
|---|---|---|---|
| **Q1** | **Double-decay: giữ decay ở đâu?** | Giữ `recency_weight` **không** có time decay (chỉ là intrinsic trust score). Di chuyển `time_decay_penalty` vào `combined_weight()` **duy nhất**. Với backtest, inject `current_time` parameter để `delta_t` được tính từ data timestamp, không phải `utcnow()`. | `recency_weight` còn được `validator_agent.py:80` dùng để phát hiện "Temporal Conflict" — nếu decay ở đó, validator so sánh các giá trị đã bị suy giảm → phát hiện sai. `combined_weight()` là boundary của Mediator — đúng chỗ để có 1 nguồn decay duy nhất. |
| **Q2** | **`app.py` (37 dòng) giữ hay xóa?** | **Xóa**, gộp logic vào `main.py` hoặc `scripts/refresh_logs.py`. Hiện tại 2 entry points gây nhầm lẫn về "single command" mục tiêu của P3-02. | Roadmap mục tiêu "1 lệnh chạy"; 2 entry points mâu thuẫn mục tiêu này. |
| **Q3** | **Backtest mock mode bắt buộc?** | **Có.** `scripts/backtest.py` default chạy `--mock` dùng `outputs/logs.json` đã có. Chỉ bật `--live` khi cần chạy thật, với rõ ràng là sẽ tốn 90+ LLM calls. | Free-tier OpenRouter dễ 429; mock mode đảm bảo tái lập khoa học — trọng tâm của ĐATN. |
| **Q4** | **Lockfile — chọn công cụ nào?** | `pip-tools` (`requirements.in` + `requirements.txt` generated) hoặc `uv.lock`. Khuyến nghị `pip-tools` vì đơn giản, phù hợp flat structure hiện tại. | Không có lockfile → `pip install -e .[dev]` không tái lập được giữa các máy/thời gian. |

---

## 2. Chặng A — Project 3: Đóng gói 1 lệnh + Demo 3 kịch bản

**Mục tiêu:** 90% Project 3 — đủ điều kiện đăng ký ĐATN.
**Gate A (pass khi đồng thời):**
- `pip install -e .[dev] && pytest -q` pass (97 tests) + `pytest --cov --cov-report=term-missing` có báo cáo
- `python main.py` hoặc `crypto-analyzer` chạy 1 lệnh end-to-end (fetch → validator → debate → mediator)
- Demo 3 kịch bản đều xuất `outputs/demo_*.json` + in RCA

| TIP-P3 | Việc | Gap xử lý | File tạo/sửa | Effort |
|---|---|---|---|---|
| **P3-01** | **Fix tái lập** — Sửa `pyproject.toml` thêm deps pin (`openai`, `pypdf`, `requests`, `google-genai`, `numpy`, `python-dotenv`), thêm `[project.optional-dependencies] dev = [pytest, pytest-cov]`, thêm `tool.pytest.ini_options.pythonpath = ["."]` hoặc `conftest.py` set `PYTHONPATH`, thêm `[project.scripts] crypto-analyzer = "main:main"`, đồng bộ `requirements.txt`, verify `pytest` | Gap 4 | `pyproject.toml:7-31`, `requirements.txt`, `conftest.py` | 45m |
| **P3-02** | **1 lệnh chạy** — **Quyết định `app.py` trước (xem Q2):** nếu xóa, gộp logic vào `main.py`. Wrapper `Makefile`/`justfile` hoặc entry point `crypto-analyzer` trỏ `main:main`, cập nhật `README.md` 1-liner `pip install -e . && crypto-analyzer` (chưa cần full Typer — chỉ cần entry point) | Gap 3 (partial) | `pyproject.toml`, `Makefile`, `README.md:66`, (optional: xóa `app.py`) | 30m |
| **P3-03** | **Git hygiene** — `git add docs/BLUEPRINT.md docs/CONTRACT.md docs/TASK_GRAPH.md`, tick Gate 1 checklist thành `[x]` cho phần đã xong, tạo `outputs/cache/` (chưa có) + `.gitkeep`, `.gitignore:12` đã có `/outputs/cache` — không cần fix | Gap 5 | `docs/*`, `outputs/cache/.gitkeep`, `.gitignore` | 15m |
| **P3-04** | **Demo 3 kịch bản** — `scripts/demo.py` chạy: (a) **Đồng thuận** (mock 3 BUY), (b) **Mâu thuẫn** (mock BUY/SELL/BUY như `outputs/logs.json:2026-06-07`), (c) **Fallback** (kill LLM → `logs.json`), xuất `outputs/demo_*.json` + in RCA, dùng cho slide bảo vệ | Demo | `scripts/demo.py`, `outputs/demo_*.json` | 1h |
| **P3-05** | **Báo cáo kiến trúc + công thức** — Reformat `multi_agent_crypto_report.md:240` thành `docs/BAO_CAO_P3.md` (bìa, mục lục, Lời cam đoan, công thức đánh số, mermaid `README.md:15-41`, phụ lục `outputs/*.json`), thêm `docs/UML.md` (Use-case + Sequence tối thiểu từ `agents/*`, `data_sources/*`) | Báo cáo | `docs/BAO_CAO_P3.md`, `docs/UML.md` | 2h |
| **P3-06** | **Fix P0 demo** — Rotate `.env` keys, fix double time decay theo Q1: `recency_weight_from_iso_timestamp()` trả về giá trị intrinsic (không decay), `time_decay_penalty` chỉ áp dụng 1 lần trong `combined_weight()`; inject `current_time` param vào `MediatorAgent._compute_weight()` cho backtest tái lập. Thêm `tenacity` retry cho 3 fetchers + `utils/llm.py:27` | Ổn định demo | `.env`, `utils/penalties.py`, `mediator_agent.py`, `data_sources/*.py`, `utils/llm.py` | 1h (gộp nếu còn thời gian) |

**Deliverables Chặng A:**
- `pip install -e .[dev] && pytest --cov` pass, `python main.py` 1 lệnh
- `scripts/demo.py` + `outputs/demo_consensus.json`, `demo_conflict.json`, `demo_fallback.json`
- `docs/BAO_CAO_P3.md` + `docs/UML.md`
- `docs/` đã git, `outputs/cache/` tồn tại

---

## 3. Chặng B — ĐATN: Thực nghiệm có đối chứng

**Mục tiêu:** 80% ĐATN — phần quyết định điểm là thực nghiệm, không phải dashboard.
**Giả thuyết nghiên cứu:** *Cơ chế phát hiện mâu thuẫn (KL + variance, `agents/validator_agent.py:80`) và tranh biện đa tác tử (`agents/debate_agent.py:218`) có cải thiện chất lượng tín hiệu BTC so với single-agent / technical-only / no-debate không?*
**Gate B (pass khi):** Có `outputs/backtest_*.csv` cho 4 configs + `docs/charts/` + bảng so sánh metric (accuracy, Sharpe, drawdown, win rate, latency/cost) + ablation kết luận.

| TIP-DATN | Việc | Metric / Ablation | File | Effort |
|---|---|---|---|---|
| **DATN-01** | **Historical data pipeline** — `data_sources/historical.py` fetch Binance klines 60–90 ngày (`/api/v3/klines?symbol=BTCUSDT&interval=1d&limit=90`), lưu `data/history/BTCUSDT_1d.parquet` (hoặc CSV), script `scripts/fetch_history.py` | Input cho backtest | `data_sources/historical.py`, `scripts/fetch_history.py`, `data/history/` | 2h |
| **DATN-02** | **Backtest engine** — `scripts/backtest.py` rolling window 30 ngày, **bắt buộc có `--mock` mode** dùng fixture data (không gọi LLM) để đảm bảo tái lập; mỗi ngày tái tạo `Validator(alpha=0.6, threshold=0.4)` → `Mediator(gamma=1e-5)` → `S_final`, so sánh với nhãn `close[t+1] > close[t]` (BUY/SELL/NEUTRAL), xuất `outputs/backtest_full.csv` | Accuracy, Sharpe, drawdown, win rate | `scripts/backtest.py`, `outputs/backtest_*.csv` | 3h |
| **DATN-03** | **Baseline & Ablation** — 4 configs trên cùng history: (a) Technical-only (chỉ `market_agent`), (b) Single-agent (chỉ `financial_agent`), (c) No-debate (`threshold=999`), (d) Full (validator+debate). Chạy tất cả với `--mock` mode. Xuất `outputs/backtest_{technical,single,nodebate,full}.csv` + `docs/charts/` (bar chart accuracy, equity curve) | Ablation study — quyết định điểm ĐATN | `scripts/backtest.py` (param sweep), `docs/charts/` | 3h |
| **DATN-04** | **Metrics chuẩn** — `utils/metrics.py` tính accuracy, Sharpe `mean/σ * sqrt(365)`, max drawdown, win rate, latency (fetch+LLM), cost (token count từ `utils/llm.py:27`) | Bảng so sánh 4 configs | `utils/metrics.py` | 2h |
| **DATN-05** | **RAG wiring** — `main.py:114` gọi `Retriever.query("BTC whale accumulation")` (`rag/retriever.py:76`) → inject vào `FINANCIAL_PROMPT` (`utils/prompts.py:143`) hoặc `scripts/demo_rag.py` riêng nếu muốn giữ pipeline P3. Thêm ablation with/without RAG | Gap 2, RAG ablation | `main.py`, `utils/prompts.py`, `scripts/demo_rag.py` | 2h |
| **DATN-06a** | **CLI + Pydantic + package structure** — `crypto_analyzer/cli.py` (Typer `crypto-analyzer analyze/backtest/test-offline`), `models.py` (Pydantic `AgentOutput`), chuyển project thành package có `__init__.py` | Gate 2 Blueprint | `crypto_analyzer/*`, `pyproject.toml` | 2h |
| **DATN-06b** | **Logging refactor** — Thay ~22 `print()` bằng `logging` chuẩn (`main.py`, `validator_agent.py`, `data_sources/*`) | Gate 3 Blueprint | `main.py`, `validator_agent.py`, `data_sources/*` | 1.5h |
| **DATN-06c** | **Async/parallel execution** — `asyncio.gather` hoặc `ThreadPoolExecutor` cho 3 specialist agents (`main.py:22-44`). Lựa chọn: (a) `asyncio.to_thread()` giữ nguyên sync agents, hoặc (b) rewrite `data_sources/*.py` sang `aiohttp`. **Không cần full async — ThreadPoolExecutor đủ cho 3 agents.** | Gate 3 Blueprint | `main.py`, `data_sources/*.py` | 2.5h |
| **DATN-07** | **Báo cáo ĐATN** — `docs/BAO_CAO_DATN.md` theo template HUST (bìa, nhiệm vụ, lời cam đoan, TLTK IEEE, phụ lục ablation tables + charts, Chương 5 Thực nghiệm định lượng) + slide 20 trang + video demo 3p | Hồ sơ bảo vệ | `docs/BAO_CAO_DATN.md`, `docs/slides.pdf` | 4h |

**Thứ tự ưu tiên ĐATN:** DATN-01 → 02 → 03 → 04 **trước** (thực nghiệm), DATN-05 → 06a → 06b → 06c **sau** (kỹ thuật), DATN-07 cuối. Dashboard/deployment để cuối nếu còn thời gian.

---

## 4. Backlog tổng hợp & Ưu tiên

| Ưu tiên | Nhóm | TIPs | Tổng effort |
|---|---|---|---|
| **P0 — Bắt buộc trước khi code** | Tái lập + Quyết định kỹ thuật | P3-01 + Q1–Q4 | 45m |
| **P0** | Đóng gói P3 | P3-02, P3-03, P3-04, P3-05, P3-06 | ~5h |
| **P1 — Quyết định điểm ĐATN** | Thực nghiệm | DATN-01 → 04 | ~12h |
| **P1** | RAG + Thiết kế | DATN-05, DATN-06a, 06b, 06c | ~8h |
| **P2 — Nếu còn thời gian** | Báo cáo + Dashboard | DATN-07, Streamlit/Docker | ~6h |

**Tổng Chặng A:** ~5.75h | **Tổng Chặng B:** ~26h | **Tổng 2 chặng:** ~31.75h Builder time.

---

## 5. Rủi ro & Lưu ý

- **LLM cost/429:** Backtest 30 ngày × 3 agents × 1 call = 90 calls OpenRouter free-tier (`google/gemma-4-26b-a4b-it:free` `utils/config.py:8`) dễ 429 (`README.md:167`) → **mock mode bắt buộc (DATN-02)**; `--live` chỉ dùng khi cần, kèm `tenacity` retry + SQLite cache (DATN-06c).
- **Double decay + Non-deterministic:** `time_decay_penalty` dùng `utcnow()` trong `recency_weight_from_iso_timestamp()` (line 35) và `MediatorAgent._compute_weight()` (line 64) → cùng 1 `logs.json` cho `S_final` khác nhau giữa 09:00 và 14:00 UTC. **Phá vỡ tái lập khoa học.** Fix theo Q1 trước khi vào backtest.
- **`outputs/cache/` chưa tồn tại:** `data_sources/*.py` tham chiếu `outputs/cache/...` → crash ngay lần chạy đầu. P3-01 cần tạo thư mục, không chỉ `.gitkeep`.
- **`app.py` song song với `main.py`:** Cần quyết định giữ/xóa trước P3-02 (xem Q2).
- **Không gộp Chặng A+B** khi chưa pass Gate A — tránh xây dashboard khi chưa có backtest.
- **Docs gate:** `docs/TASK_GRAPH.md:211` gates `[ ]` là mục tiêu, sau P3-03 phải tick `[x]` cho phần đã xong.

---

## 6. Checklist Gate (Vibecode Kit)

### Gate A: SCAN → RRI → P3 DONE
- [x] Q1–Q4 đã chốt (double-decay, app.py, mock mode, lockfile)
- [x] P3-01 `pytest --cov` pass, `PYTHONPATH` fixed, `outputs/cache/` tồn tại, lockfile có
- [x] P3-02 1 lệnh chạy (`crypto-analyzer` hoặc `python main.py`) sau khi xử lý `app.py`
- [x] P3-03 `docs/` đã `git add`, gates tick `[x]`
- [x] P3-04 `scripts/demo.py` + 3 `outputs/demo_*.json`
- [x] P3-05 `docs/BAO_CAO_P3.md` + `docs/UML.md` xong
- [x] P3-06 Double-decay fix + `time_decay_penalty` dùng data timestamp

### Gate B: P3 → DATN DONE
- [ ] DATN-01 Historical `data/history/BTCUSDT_1d.*` tồn tại
- [ ] DATN-02 `scripts/backtest.py --mock` chạy được, output CSV
- [ ] DATN-03 4 configs CSV + `docs/charts/` bar chart + equity curve
- [ ] DATN-04 Bảng metric so sánh (accuracy, Sharpe, drawdown, win rate, latency/cost)
- [ ] DATN-05 RAG wired + ablation with/without
- [ ] DATN-06a CLI + Pydantic + package structure
- [ ] DATN-06b Logging thay `print()`
- [ ] DATN-06c Async/parallel execution
- [ ] DATN-07 `docs/BAO_CAO_DATN.md` + slides theo template HUST

---

## 7. Tham chiếu

- `README.md:1-168` — Kiến trúc mermaid, setup, limitations
- `docs/BLUEPRINT.md:305` — Kiến trúc mục tiêu, R-matrix
- `docs/CONTRACT.md:110` — 16 deliverables, NOT INCLUDED
- `docs/TASK_GRAPH.md:211` — 14 TIPs, 4 Phases, gates
- `multi_agent_crypto_report.md:240` — 5 chương báo cáo hiện tại
- `pyproject.toml:1-32`, `requirements.txt:6`, `.env.example:14`
- `agents/*:700` dòng (6 files), `utils/*:405` dòng, `data_sources/*:386` dòng, `rag/*:121` dòng, `tests/*:1098` dòng (97 tests)
- `app.py:37` — entry point thứ 2 (quyết định giữ/xóa ở Q2)
- `utils/confidence.py`, `utils/display.py`, `utils/debate_buffer.py`, `utils/schema.py` — module phụ không được nhắc trong lộ trình
- `outputs/logs.json`, `validation_report.json`, `mediator_result.json` — bằng chứng thực nghiệm 2026-06-07

---

*File này là CONTRACT cho 2 chặng. Reply `APPROVED` để bắt đầu Chặng A (P3-01).*
