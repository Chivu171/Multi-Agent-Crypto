# BLUEPRINT: Multi-Agent-Crypto
## Vibecode Kit v6.0

> **⚠️ ARCHITECTURAL REFERENCE ONLY — superseded by `docs/LO_TRINH_P3_DATN.md` for execution.**
> This file is retained for design context. For current task breakdown, gates, effort estimates, and execution order, see `docs/LO_TRINH_P3_DATN.md`.

### PROJECT INFO
| Field | Value |
|-------|-------|
| Project | Multi-Agent-Crypto Financial Analysis & Conflict Resolution System |
| Nature | CLI Tool + Batch Pipeline + Research Archive |
| Date | 2026-08-07 |
| Status | APPROVED — awaiting CONTRACT |

---

### GOALS

**Primary Goal:** Xây dựng hệ thống phân tích tài chính crypto đa đại lý với cơ chế tranh biện tự động, đủ rigor để publish paper và đủ reliability để làm production trading signal tool.

**Target Audience:** Solo researcher (bạn) — vừa để viết paper, vừa để experiment với trading signals.

**Key Message:** "Hệ thống không tin tưởng LLM mù quáng — nó đo lường mâu thuẫn bằng toán học, tranh biện để tìm sự thật, rồi mới ra quyết định."

---

### ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CLI ENTRY POINT                              │
│                    (Typer: `crypto-analyzer`)                       │
│  Commands: analyze, backtest, test-offline, migrate-to-rag           │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
              ▼                ▼                ▼
     ┌────────────────┐ ┌─────────────┐ ┌────────────────┐
     │  Financial     │ │   Market    │ │   Sentiment    │
     │   Agent        │ │   Agent     │ │    Agent       │
     │ (BaseAgent)    │ │ (BaseAgent) │ │  (BaseAgent)   │
     └───────┬────────┘ └──────┬──────┘ └───────┬────────┘
             │                 │                 │
             └─────────────────┼─────────────────┘
                               │
                               ▼
                 ┌─────────────────────────┐
                 │    Validator Agent      │
                 │  (KL Divergence +       │
                 │   Variance Hybrid)      │
                 └───────────┬─────────────┘
                             │
                    ┌────────┴────────┐
                    │                 │
              Conflict?              No Conflict
                    │                 │
                    ▼                 ▼
          ┌─────────────────┐  ┌──────────────┐
          │   Debate Agent  │  │   Mediator   │
          │ (3 rounds,      │  │   Agent      │
          │  confidence     │  │ (Penalties)  │
          │   decay)        │  └──────┬───────┘
          └────────┬────────┘         │
                   │                  │
                   └────────┬─────────┘
                            │
                            ▼
                  ┌─────────────────────┐
                  │   Output Layer      │
                  │  (Pydantic → JSON   │
                  │   + Console Report) │
                  └─────────────────────┘
```

#### Component Details

| Block | Responsibility | Implementation |
|-------|---------------|----------------|
| **CLI** | Entry point, args, subcommands | Typer (`cli.py`) |
| **BaseAgent** | Abstract interface | ABC + Pydantic BaseModel |
| **LLM Provider** | Strategy pattern cho OpenRouter/Anthropic/Google/local | ABC + implementations trong `llm/` |
| **Caching** | Prompt hash → SQLite cache, TTL 24h | `cache/sqlite_cache.py` |
| **RAG Module** | ChromaDB + embeddings + retriever | `rag/` — Phase 2 |
| **Specialist Agents** | Financial, Market, Sentiment | Pydantic models, inherits BaseAgent |
| **Validator** | KL + Variance + Classification | NumPy, proven math |
| **Debate** | Multi-round, rebuttal strength, confidence decay | NumPy + LLM |
| **Mediator** | Penalties + weighted consensus | NumPy, proven math |
| **Output** | JSON serialization, report generation | Pydantic + Jinja2 |
| **Tests** | pytest + mock, 80%+ coverage | `tests/` |

---

### DESIGN SYSTEM

*Not applicable — CLI tool, no UI.*

### CLI Design Direction

| Element | Decision | Rationale |
|---------|----------|-----------|
| Command naming | `crypto-analyzer analyze`, `crypto-analyzer backtest` | Verb-first, clear intent |
| Output format | JSON (default) + `--report` for human-readable | Machine-readable for research, human-friendly for ad-hoc |
| Exit codes | 0 = success, 1 = pipeline error, 2 = LLM failure | Standard Unix conventions |
| Verbosity | `--verbose` / `--quiet` flags | Solo researcher workflow |

---

### TECH STACK

#### Reuse from Existing Codebase
| Component | Keep | Rationale |
|-----------|------|-----------|
| Python 3.11 | ✅ | Stable, ecosystem |
| NumPy | ✅ | Math core (KL, variance, penalties) |
| OpenAI SDK | ✅ | LLM client (OpenRouter compatible) |
| `utils/prompts.py` | ✅ | Prompt templates — refactor structure only |
| `utils/penalties.py` | ✅ | Penalty functions — proven math |
| `utils/confidence.py` | ✅ | Confidence decay — proven formula |
| `agents/mediator_agent.py` | ✅ | Mediator logic — proven |
| `agents/validator_agent.py` | ✅ | Validator math — proven |

#### Add / Replace
| Component | Add | Rationale |
|-----------|-----|-----------|
| **Pydantic BaseModel** | ✅ | Type safety, validation, serialization |
| **Typer** | ✅ | CLI framework — subcommands, help text |
| **pytest + pytest-cov** | ✅ | 80%+ test coverage |
| **ChromaDB** | ✅ | Vector store cho RAG |
| **sentence-transformers** | ✅ | Embedding model cho RAG |
| **Celery + Redis** | ✅ | Batch queue cho backtest |
| **SQLite cache** | ✅ | LLM response caching |
| **logging** | ✅ | Structured logging |
| **pyproject.toml** | ✅ | Dependency management |
| **ABC (abc.py)** | ✅ | Base Agent interface |
| **asyncio** | ✅ | Parallel agent execution |
| **Jinja2** | ✅ | Report template rendering |
| **python-dotenv** | ✅ | Env config |

#### Remove
| Component | Action | Reason |
|-----------|--------|--------|
| `app.py` | Delete | Redundant với main pipeline |
| `agents/debate_module.py` | Delete | Empty placeholder, logic đã có trong debate_agent.py |
| `rag/ingest_pdf.py` | Delete | Không cần PDF ingestion |
| `utils/embeddings.py` | Delete | Placeholder, sẽ thay bằng ChromaDB |
| `utils/scoring.py` | Delete | Empty placeholder, no clear use case |

---

### FILE STRUCTURE

```
Multi-Agent-Crypto/
├── crypto_analyzer/                 # Main package
│   ├── __init__.py
│   ├── cli.py                       # Typer CLI entry point
│   ├── config.py                    # Settings, env vars
│   ├── models.py                    # Pydantic BaseModels (AgentOutput, etc.)
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py                  # BaseAgent ABC
│   │   ├── financial.py             # Financial Agent
│   │   ├── market.py                # Market Agent
│   │   ├── sentiment.py             # Sentiment Agent
│   │   ├── validator.py             # Validator Agent
│   │   ├── debate.py                # Debate Agent
│   │   └── mediator.py              # Mediator Agent
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── provider.py              # LLMProvider ABC
│   │   ├── openrouter.py            # OpenRouter implementation
│   │   ├── anthropic.py             # Anthropic implementation
│   │   ├── google.py                # Google implementation
│   │   └── local.py                 # Local/LM Studio implementation
│   ├── rag/
│   │   ├── __init__.py
│   │   ├── chunking.py              # Text chunking strategies
│   │   ├── embeddings.py            # Embedding wrapper
│   │   ├── retriever.py             # ChromaDB retriever
│   │   └── ingest.py                # Data ingestion pipeline
│   ├── pipeline.py                  # Main pipeline orchestration
│   ├── cache.py                     # SQLite LLM cache
│   └── utils.py                     # Helper functions
├── utils/                           # Legacy utilities (keep during migration)
│   ├── config.py
│   ├── llm.py
│   ├── belief.py
│   ├── schema.py
│   ├── prompts.py
│   ├── penalties.py
│   ├── confidence.py
│   └── display.py
├── agents/                          # Legacy agents (keep during migration)
│   ├── financial_agent.py
│   ├── market_agent.py
│   ├── sentiment_agent.py
│   ├── validator_agent.py
│   ├── debate_agent.py
│   └── mediator_agent.py
├── data/                            # Static data (Phase 1)
│   ├── financial_report.txt
│   ├── market_data.txt
│   └── sentiment_news.txt
├── outputs/                         # Generated outputs
│   ├── logs.json
│   ├── mediator_result.json
│   ├── validation_report.json
│   └── debate_history.json
├── tests/
│   ├── __init__.py
│   ├── conftest.py                  # Shared fixtures
│   ├── fixtures/                    # Test data
│   │   ├── sample_agents_output.json
│   │   └── mock_llm_responses.json
│   ├── test_validator.py
│   ├── test_mediator.py
│   ├── test_penalties.py
│   ├── test_confidence.py
│   ├── test_debate.py
│   ├── test_agents.py
│   └── test_pipeline.py
├── docs/                            # Documentation
│   ├── BLUEPRINT.md
│   ├── CONTRACT.md
│   ├── TASK_GRAPH.md
│   └── ARCHITECTURE.md
├── TIPs/                            # Task Instruction Packs
│   ├── TIP-001.md
│   ├── TIP-002.md
│   └── ...
├── pyproject.toml                   # Dependency manifest
├── .env.example                     # Env template
├── main.py                          # Legacy entry (deprecated)
├── README.md                        # Project README
└── LICENSE
```

---

### RRI REQUIREMENTS MAPPING

| Blueprint Section | Requirements | Source (RRI Q#) |
|-------------------|-------------|-----------------|
| CLI Commands | R11 | Q38 |
| BaseAgent + Pydantic | R7, R8 | Q29, Q32, Q35 |
| LLM Provider Strategy | R9 | Q31 |
| Parallel Execution | R8 | Q30 |
| RAG (ChromaDB) | R5 | Q15, Q37 |
| LLM Caching | R10 | Q33 |
| Offline/Mock Mode | R6 | Q20 |
| Batch Backtest | R13 | Q24 |
| Queue (Celery/Redis) | R15 | Q46 |
| Monitoring + Alerting | R14, R15 | Q41, Q42 |
| Test Coverage 80%+ | R12 | Q21, Q27 |
| Retry on LLM failure | R18 | Q22 |
| Deterministic Behavior | R6 | Q20 |
| Cost Control | R19 | Q43 |
| Security | R20 | Q47 |

---

### TASK DECOMPOSITION PREVIEW

```
Phase 1: Foundation (Blocking cho Paper)
├── TIP-001: Scaffold project structure + pyproject.toml + base classes
├── TIP-002: Refactor agents to BaseAgent + Pydantic models
├── TIP-003: Replace json.loads with Pydantic validation
├── TIP-004: Add pytest suite (Validator + Mediator + Penalties)
├── TIP-005: Add Typer CLI (analyze, backtest, test-offline)
├── TIP-006: Add logging + offline/mock mode
└── [Phase 1 Gate]

Phase 2: RAG Implementation (Bắt buộc cho paper)
├── TIP-007: Implement ChromaDB retriever + embeddings
├── TIP-008: Implement chunking strategy for BTC data
├── TIP-009: Replace static file reads with dynamic retrieval
├── TIP-010: Add SQLite LLM cache layer
└── [Phase 2 Gate]

Phase 3: Hardening & Research Tooling
├── TIP-011: Parallel agent execution (asyncio)
├── TIP-012: LLM Provider Strategy pattern
├── TIP-013: Add batch backtest command
├── TIP-014: Add monitoring metrics + alerting
└── [Phase 3 Gate]

Phase 4: Production Readiness (Optional)
├── TIP-015: Dockerfile + docker-compose
├── TIP-016: API key rotation + rate limiting
├── TIP-017: Backup strategy + disaster recovery
└── [Phase 4 Gate]
```

**Estimated Effort:** ~14 TIPs, estimated 8-12 hours Claude Code time

---

### CHECKPOINT

- [x] Architecture matches expectations (multi-agent pipeline + RAG + caching)
- [ ] Design is appropriate (CLI — no UI needed)
- [x] Requirements are complete (from RRI)
- [x] Task decomposition is reasonable
- [x] Nothing important is missing

**Reply "APPROVED" to receive CONTRACT.**
