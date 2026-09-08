# Multi-Agent Crypto

![status](https://img.shields.io/badge/status-research%20prototype-orange)
![python](https://img.shields.io/badge/python-3.11%2B-blue)
![license](https://img.shields.io/badge/license-unspecified-lightgrey)

A multi-agent LLM pipeline for crypto market analysis. Three specialist agents (financial/on-chain, market/technical, sentiment) each produce an independent belief vector; a validator agent quantifies disagreement between them (KL-divergence + variance); when conflict is high, a debate agent runs multi-round reconciliation; a mediator agent aggregates everything into a final weighted decision (BUY / SELL / NEUTRAL).

> **Status: research prototype.** The specialist agents currently read static text files under `data/`, not a live market-data feed. See [Limitations](#limitations).

---

## Architecture

```mermaid
flowchart LR
    subgraph Specialists["Specialist Agents (independent)"]
        direction TB
        FIN["💰 Financial Agent<br/>on-chain fundamentals"]
        MKT["📈 Market Agent<br/>technical indicators"]
        SEN["📰 Sentiment Agent<br/>news / social"]
    end

    VAL{{"⚖️ Validator Agent<br/>conflict score = KL-divergence + variance"}}
    DEB(["🗣️ Debate Agent<br/>multi-round rebuttal, confidence decay"])
    MED["🧮 Mediator Agent<br/>S_final = Σ dᵢ·sᵢ·ωᵢ"]
    OUT(["✅ Final signal: BUY / SELL / NEUTRAL"])

    FIN --> VAL
    MKT --> VAL
    SEN --> VAL
    VAL -->|conflict low| MED
    VAL -->|conflict high| DEB
    DEB --> MED
    MED --> OUT

    style Specialists fill:#eef4ff,stroke:#7aa2f7,color:#1a1a1a
    style VAL fill:#fff4e6,stroke:#f5a623,color:#1a1a1a
    style DEB fill:#ffecec,stroke:#e05555,color:#1a1a1a
    style MED fill:#eafaf1,stroke:#2ecc71,color:#1a1a1a
    style OUT fill:#2ecc71,stroke:#27ae60,color:#ffffff
```

| Component | File | Responsibility |
|---|---|---|
| Financial Agent | `agents/financial_agent.py` | Reads a static on-chain report, asks the LLM for a signal + belief vector |
| Market Agent | `agents/market_agent.py` | Reads a static technical report, asks the LLM for a signal + belief vector |
| Sentiment Agent | `agents/sentiment_agent.py` | Reads a static news/sentiment report, asks the LLM for a signal + belief vector |
| Validator Agent | `agents/validator_agent.py` | Computes a hybrid conflict score (mean pairwise KL-divergence + decision variance), classifies conflict type, triggers root-cause analysis + debate above threshold |
| Debate Agent | `agents/debate_agent.py` | Multi-round adversarial debate; confidence decays per round based on rebuttal strength (cosine / Jaccard / Levenshtein distance) |
| Mediator Agent | `agents/mediator_agent.py` | Aggregates final belief vectors into `S_final = Σ dᵢ·sᵢ·ωᵢ` with entropy / redundancy / time-decay penalties (`utils/penalties.py`) |
| LLM client | `utils/llm.py`, `utils/config.py` | Prefers OpenRouter if `OPENROUTER_API_KEY` is set, otherwise falls back to a local LM Studio server |

---

## Setup

Requires **Python 3.11+**.

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# or: pip install -e .
```

Copy the env template and fill in your credentials:

```bash
cp .env.example .env
```

| Backend | When it's used | What to set |
|---|---|---|
| **OpenRouter** (preferred) | `OPENROUTER_API_KEY` is non-empty | `OPENROUTER_API_KEY` — get one at [openrouter.ai](https://openrouter.ai) |
| **LM Studio** (local fallback) | `OPENROUTER_API_KEY` is empty | Run [LM Studio](https://lmstudio.ai) locally, serving on `http://127.0.0.1:1234/v1`, with a model matching `DEFAULT_MODEL` |

---

## Running

```bash
python main.py
```

This runs the full pipeline — specialist agents → validator → (conditional) debate → mediator — and prints the reasoning steps and final decision to the console. If none of the specialist agents can reach the LLM, `main.py` automatically falls back to the cached output in `outputs/logs.json`.

Ad-hoc smoke-test scripts (not a real test suite yet — see [Limitations](#limitations)):

```bash
python test.py            # basic LLM connectivity check
python test_debate.py     # exercises the debate agent
python test_validator.py  # exercises the validator agent
```

---

## Project layout

```text
Multi-Agent-Crypto/
├── agents/     agent implementations (financial, market, sentiment, validator, debate, mediator)
├── utils/      LLM client, config, prompts, math helpers (penalties, confidence, belief vectors)
├── data/       static input reports consumed by the specialist agents
├── outputs/    run artifacts (logs.json, mediator_result.json, validation_report.json)
├── rag/        placeholder for a planned retrieval-augmented pipeline (not implemented yet)
├── docs/       planning docs for a larger refactor (not yet applied to the code)
└── TIPs/       task specs for the refactor described in docs/
```

---

## Limitations

- **No live data feed** — `data/*.txt` are manually written/curated files, not pulled from any API (Glassnode, CoinGlass, exchanges, etc.).
- **No automated test suite** — `test*.py` at the repo root are manual smoke scripts, not pytest-based tests.
- **`rag/` is unimplemented** — empty stub files; retrieval-augmented context is planned but not built.
- Some per-agent "entropy/redundancy" metadata values are hand-set constants rather than computed from data.
- `app.py` is a legacy/simplified alternate entry point; `main.py` is the canonical one to use.

See `docs/BLUEPRINT.md`, `docs/CONTRACT.md`, `docs/TASK_GRAPH.md`, and `TIPs/TIP-001.md`–`TIP-007.md` for the planned refactor (packaging, CLI, Pydantic models, RAG, test coverage) — none of it has landed in the code yet.
