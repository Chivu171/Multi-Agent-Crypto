# TASK GRAPH: Multi-Agent-Crypto

## Vibecode Kit v6.0

> **⚠️ DEPRECATED — current task graph is `docs/LO_TRINH_P3_DATN.md`.**
> Phase structure and TIP numbering have been replaced by Chặng A/B and P3/DATN tasks in the roadmap.

### OVERVIEW

| Metric | Value |
|--------|-------|
| Total TIPs | 14 |
| Phases | 4 |
| Estimated Effort | 8-12 hours Claude Code time |
| Critical Path | TIP-001 → TIP-002 → TIP-003 → TIP-005 → TIP-006 |

---

### PHASE 1: Foundation (Blocking cho Paper)

**Goal:** Refactor codebase thành architecture sạch, có types, có tests, có CLI.

```
TIP-001: Scaffold project structure + pyproject.toml + base classes
    │
    ▼
TIP-002: BaseAgent + Pydantic models ───────────────┐
    │                                                │
    ▼                                                │
TIP-003: Refactor agents to BaseAgent               │
    │                                                │
    ▼                                                │
TIP-004: Replace json.loads with Pydantic           │
    │                                                │
            ┌───────────────────────┐               │
            │                       │               │
            ▼                       ▼               ▼
    TIP-005: Typer CLI      TIP-006: pytest suite   TIP-007: Logging + Offline Mode
            │                                               │
            └───────────────────────┬───────────────────────┘
                                    │
                                    ▼
                          [PHASE 1 GATE]
```

**Dependencies:**
- TIP-002 phải hoàn thành trước TIP-003, TIP-006
- TIP-003 phải hoàn thành trước TIP-004 (cần Pydantic models)
- TIP-005 có thể song song với TIP-004, TIP-006
- TIP-001 là foundation cho tất cả

**Deliverables:**
- `crypto_analyzer/` package với module structure
- `pyproject.toml` + lockfile
- `BaseAgent` ABC + `AgentOutput` Pydantic model
- 3 specialist agents refactored
- CLI: `crypto-analyzer analyze`, `crypto-analyzer backtest`, `crypto-analyzer test-offline`
- pytest suite: `test_validator.py`, `test_mediator.py`, `test_penalties.py`
- Logging + offline/mock mode

---

### PHASE 2: RAG Implementation (Bắt buộc cho Paper)

**Goal:** Thay thế static file reads bằng dynamic retrieval từ ChromaDB.

```
TIP-008: ChromaDB setup + retriever ─────────────────┐
    │                                                  │
    ▼                                                  │
TIP-009: Chunking strategy for BTC data               │
    │                                                  │
    ▼                                                  │
TIP-010: Replace static reads with dynamic retrieval ◄┘
    │
    ▼
TIP-011: SQLite LLM cache layer
    │
    ▼
[PHASE 2 GATE]
```

**Dependencies:**
- TIP-008 phải hoàn thành trước TIP-009, TIP-010
- TIP-010 phải hoàn thành trước TIP-011 (cần agent outputs để cache)
- TIP-011 có thể song song với TIP-010

**Deliverables:**
- `rag/` module: chunking, embeddings, retriever, ingest
- ChromaDB persist directory
- Dynamic retrieval trong 3 specialist agents
- SQLite cache cho LLM responses

---

### PHASE 3: Hardening & Research Toolging

**Goal:** Parallel execution, batch backtest, monitoring.

```
TIP-012: Parallel agent execution (asyncio) ─────────┐
    │                                                  │
    ▼                                                  │
TIP-013: LLM Provider Strategy pattern               │
    │                                                  │
    ▼                                                  │
TIP-014: Batch backtest command (Celery/Redis) ◄──────┘
    │
    ▼
TIP-015: Monitoring + alerting
    │
    ▼
[PHASE 3 GATE]
```

**Dependencies:**
- TIP-012 phải hoàn thành trước TIP-014 (parallel cần thiết cho batch)
- TIP-013 phải hoàn thành trước TIP-014 (cần Provider abstraction cho batch)
- TIP-015 có thể song song với TIP-014

**Deliverables:**
- Async pipeline execution
- LLM Provider ABC + implementations
- `crypto-analyzer backtest` command
- Metrics: latency, conflict rate, S_final distribution, cost
- Alerting hooks

---

### PHASE 4: Production Readiness (Optional)

**Goal:** Deployment artifacts, security, backup.

```
TIP-016: Dockerfile + docker-compose
    │
    ▼
TIP-017: API key rotation + rate limiting
    │
    ▼
TIP-018: Backup strategy + disaster recovery
    │
    ▼
[PHASE 4 GATE]
```

**Dependencies:**
- TIP-016 là foundation cho TIP-017, TIP-018
- Có thể skip nếu không cần deploy

**Deliverables:**
- Dockerfile + docker-compose.yml
- API key rotation mechanism
- Rate limiting wrapper
- Backup scripts + DR plan

---

### CRITICAL PATH

```
TIP-001 → TIP-002 → TIP-003 → TIP-004 → TIP-005 → TIP-006
                                                      │
TIP-008 → TIP-009 → TIP-010 → TIP-011 → TIP-012 → TIP-013 → TIP-014
```

**Longest path:** TIP-001 → TIP-002 → TIP-003 → TIP-004 → TIP-005 → TIP-006 → TIP-008 → TIP-009 → TIP-010 → TIP-011 → TIP-012 → TIP-013 → TIP-014

**Estimated time on critical path:** ~10-12 hours

---

### RISK MITIGATION IN TASK GRAPH

| Risk | Mitigation in TIPs |
|------|-------------------|
| Determinism bị LLM randomness phá vỡ | TIP-006 (offline/mock mode) + TIP-011 (cache) |
| RAG phức tạp hơn dự kiến | TIP-008 (ChromaDB local, simple setup) + TIP-009 (incremental migration) |
| Celery/Redis quá nặng | TIP-014 (fallback sang asyncio.Queue nếu batch nhỏ) |
| Pydantic migration phá vỡ existing logic | TIP-003 (incremental, từng agent một) + TIP-004 (tests verify) |

---

### GATE CRITERIA

**Phase 1 Gate (sau TIP-007):**
- [ ] `crypto-analyzer analyze` chạy thành công với data tĩnh
- [ ] pytest coverage ≥ 80% cho validator, mediator, penalties
- [ ] Offline mode hoạt động deterministic
- [ ] Logging hoạt động (file + console)

**Phase 2 Gate (sau TIP-011):**
- [ ] ChromaDB index được build từ data/*.txt
- [ ] Agents đọc từ ChromaDB thay vì static files
- [ ] LLM cache hoạt động (same prompt → same response)
- [ ] Cache TTL 24h hoạt động

**Phase 3 Gate (sau TIP-015):**
- [ ] `crypto-analyzer backtest` chạy batch 10-50 analyses
- [ ] Parallel execution giảm latency ≥ 50%
- [ ] Monitoring metrics được log
- [ ] Alerting hooks hoạt động

**Phase 4 Gate (sau TIP-018):**
- [ ] Docker build thành công
- [ ] API key rotation mechanism hoạt động
- [ ] Backup script chạy thành công
- [ ] DR plan được document

---

### CONFIRM

Reply **"CONFIRM"** to receive Task Instruction Packs (TIPs) for BUILD phase.
