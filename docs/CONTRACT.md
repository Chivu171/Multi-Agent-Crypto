# CONTRACT: Multi-Agent-Crypto
## Vibecode Kit v6.0

> **⚠️ DEPRECATED — active contract is `docs/LO_TRINH_P3_DATN.md`.**
> This file is no longer updated. Deliverables and scope are tracked in the roadmap file.

### DELIVERABLES

| # | Item | Details | Requirements |
|---|------|---------|--------------|
| 1 | **CLI Tool** `crypto-analyzer` | Typer-based CLI với subcommands: `analyze`, `backtest`, `test-offline` | R11, CLI design |
| 2 | **BaseAgent Architecture** | ABC + Pydantic BaseModel cho tất cả agents | R7, R8, Q29, Q32, Q35 |
| 3 | **Specialist Agents** (Financial, Market, Sentiment) | Refactor từ standalone functions sang BaseAgent classes | R1 |
| 4 | **Validator Agent** | Giữ nguyên math core (KL + Variance), thêm Pydantic output | R2 |
| 5 | **Debate Agent** | Giữ nguyên logic, refactor sang BaseAgent | R3 |
| 6 | **Mediator Agent** | Giữ nguyên logic, refactor sang BaseAgent | R4 |
| 7 | **LLM Provider Abstraction** | Strategy pattern: OpenRouter, Anthropic, Google, Local | R9, Q31 |
| 8 | **LLM Caching Layer** | SQLite cache, prompt hash key, TTL 24h | R10, Q33 |
| 9 | **RAG Module** | ChromaDB + sentence-transformers + retriever | R5, Q15, Q37 |
| 10 | **Parallel Execution** | asyncio cho 3 specialist agents | R8, Q30 |
| 11 | **Offline/Mock Mode** | Deterministic test mode cho paper experiments | R6, Q20 |
| 12 | **Batch Backtest** | Celery + Redis queue, 10-50 analyses | R13, Q24, Q46 |
| 13 | **Monitoring + Alerting** | Metrics: latency, conflict rate, S_final, cost | R14, R15, Q41, Q42 |
| 14 | **Test Suite** | pytest + mock, 80%+ coverage cho core modules | R12, Q21, Q27 |
| 15 | **Logging** | Structured logging, file + console | Q34 implied |
| 16 | **Dependency Manifest** | pyproject.toml + lockfile | R20, Q36 |

---

### TECH STACK

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Language | Python 3.11 | Existing codebase, ecosystem |
| CLI | Typer | Modern, type-safe, auto-help |
| Data Models | Pydantic BaseModel | Validation, serialization, type safety |
| LLM Client | OpenAI SDK | OpenRouter compatible, Anthropic/Google via base_url |
| Vector Store | ChromaDB | Local-first, deterministic, open-source |
| Embeddings | sentence-transformers | Local, no API cost, deterministic |
| Queue | Celery + Redis | Scalable batch processing |
| Cache | SQLite | Simple, local, no external dependency |
| Testing | pytest + pytest-cov + unittest.mock | Industry standard |
| Logging | Python logging module | Structured, levels, file + console |
| Build | pyproject.toml + uv/poetry lockfile | Reproducible environment |

---

### TASK GRAPH SUMMARY

**Total TIPs:** 14 (Phase 1-3)
**Estimated Effort:** 8-12 hours Claude Code time

```
TIP-001: Scaffold ──────────────────────────────┐
    │                                            │
    ▼                                            │
TIP-002: BaseAgent + Pydantic ───────┐           │
    │                                │           │
    ▼                                ▼           ▼
TIP-003: Refactor Agents    TIP-004: pytest   TIP-005: CLI
    │                        suite             │
    │                                │           │
    ▼                                ▼           ▼
TIP-006: Logging + Offline Mode ◄───────────────┘
    │
    ▼
TIP-007: RAG ChromaDB ─────────────────────────┐
    │                                           │
    ▼                                           │
TIP-008: Chunking Strategy                     │
    │                                           │
    ▼                                           │
TIP-009: Dynamic Retrieval ◄───────────────────┘
    │
    ▼
TIP-010: LLM Cache Layer
    │
    ▼
TIP-011: Parallel Execution ───────────────────┐
    │                                           │
    ▼                                           │
TIP-012: LLM Provider Strategy                 │
    │                                           │
    ▼                                           │
TIP-013: Batch Backtest ◄──────────────────────┘
    │
    ▼
TIP-014: Monitoring + Alerting
    │
    ▼
[VERIFY]
```

---

### NOT INCLUDED

| Item | Reason |
|------|--------|
| Multi-asset support (ETH, SOL, etc.) | Scope control — BTC only for research |
| Multi-user / auth | Solo researcher only |
| Web UI / Dashboard | CLI is sufficient for research workflow |
| Docker / Deployment automation | Deferred — local development first |
| Real-time streaming data | Static data + RAG sufficient for paper |
| PDF ingestion | Không cần cho nghiên cứu BTC |
| Advanced RAG (hybrid search, reranking) | Phase 2+ if needed |
| Production hardening (rate limiting, circuit breakers) | Research tool, not production service yet |

---

### CONFIRM

Reply **"CONFIRM"** to receive Task Graph (TIPs).
