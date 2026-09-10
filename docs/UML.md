# UML Diagrams — Multi-Agent-Crypto

## Use-case Diagram

```mermaid
usecaseDiagram
    actor Researcher
    actor LLM_Service
    actor Data_API

    Researcher --> (Run Full Pipeline)
    Researcher --> (Refresh Cache)
    Researcher --> (Run Demo Scenarios)
    Researcher --> (Run Tests)

    (Run Full Pipeline) --> (Fetch Live Data)
    (Run Full Pipeline) --> (Validate Conflict)
    (Run Full Pipeline) --> (Run Debate)
    (Run Full Pipeline) --> (Aggregate Signal)
    (Run Full Pipeline) --> (Fallback to Cache)

    (Fetch Live Data) --> Data_API : Binance / blockchain.info / Alternative.me
    (Run Full Pipeline) --> LLM_Service : ask_llm()

    (Validate Conflict) --> (Compute KL Divergence)
    (Validate Conflict) --> (Compute Variance)
    (Validate Conflict) --> (Classify Conflict)

    (Run Debate) --> (Update Confidence)
    (Run Debate) --> (Rebuttal Strength)

    (Aggregate Signal) --> (Compute Weights)
    (Aggregate Signal) --> (Compute S_final)
```

## Sequence Diagram — Full Pipeline

```mermaid
sequenceDiagram
    actor User
    participant Main
    participant Financial
    participant Market
    participant Sentiment
    participant Validator
    participant Debate
    participant Mediator
    participant LLM
    participant Cache

    User->>Main: python main.py
    Main->>Financial: run()
    Main->>Market: run()
    Main->>Sentiment: run()

    par Parallel agents
        Financial->>LLM: ask_llm(prompt)
        Financial->>Cache: fetch_onchain_data()
    and
        Market->>LLM: ask_llm(prompt)
        Market->>Cache: fetch_market_data()
    and
        Sentiment->>LLM: ask_llm(prompt)
        Sentiment->>Cache: fetch_sentiment_data()
    end

    alt All agents fail
        Main->>Cache: Load outputs/logs.json
    else At least one succeeds
        Main->>Main: Save outputs/logs.json
    end

    Main->>Validator: evaluate_pipeline(outputs)
    Validator->>Validator: calculate_conflict_core()
    Validator->>Validator: classify_conflict()

    alt conflict_score >= threshold
        Validator->>Debate: run_debate(outputs)
        Debate->>Debate: Multi-round rebuttal
        Debate-->>Validator: debate_updated_outputs
    end

    Validator-->>Main: validation_result
    Main->>Mediator: run_mediator(final_outputs)
    Mediator->>Mediator: aggregate()
    Mediator-->>Main: mediator_result

    Main->>User: Print S_final + RCA report
```

## Sequence Diagram — Mock/Demo Pipeline

```mermaid
sequenceDiagram
    actor User
    participant Demo
    participant Validator
    participant Debate
    participant Mediator

    User->>Demo: python scripts/demo.py

    Demo->>Demo: Generate mock outputs (consensus/conflict/fallback)

    Demo->>Validator: evaluate_pipeline(mock_outputs)
    Validator->>Validator: calculate_conflict_core()
    Validator->>Validator: classify_conflict()

    alt conflict detected
        Validator->>Debate: run_debate()
        Debate-->>Validator: updated outputs
    end

    Validator-->>Demo: validation_result
    Demo->>Mediator: run_mediator(outputs)
    Mediator-->>Demo: mediator_result

    Demo->>Demo: Save outputs/demo_*.json
    Demo->>User: Print results + RCA
```

## Class Diagram (Core)

```mermaid
classDiagram
    class MediatorAgent {
        -gamma: float
        +_compute_weight(meta, current_time) float
        +aggregate(agents_output, current_time) dict
    }

    class ValidatorAgent {
        -alpha: float
        -threshold: float
        -use_llm: bool
        +calculate_conflict_core(outputs) tuple
        +classify_conflict(outputs, score) list
        +run_root_cause_analysis(outputs, categories) str
        +evaluate_pipeline(outputs) dict
    }

    class DebateAgent {
        -rounds: int
        -alpha: float
        -buffer: DebateBuffer
        +run_debate(outputs) list
    }

    class SpecialistAgent {
        <<interface>>
        +run() dict
    }

    class FinancialAgent {
        +run() dict
    }

    class MarketAgent {
        +run() dict
    }

    class SentimentAgent {
        +run() dict
    }

    SpecialistAgent <|.. FinancialAgent
    SpecialistAgent <|.. MarketAgent
    SpecialistAgent <|.. SentimentAgent

    ValidatorAgent --> DebateAgent : triggers
    ValidatorAgent ..> SpecialistAgent : validates
    DebateAgent ..> SpecialistAgent : updates
    MediatorAgent ..> SpecialistAgent : aggregates
```

## Component Diagram

```mermaid
flowchart TB
    subgraph Entry["Entry Points"]
        main["main.py"]
        demo["scripts/demo.py"]
        refresh["scripts/refresh_logs.py"]
    end

    subgraph Agents["Agent Layer"]
        fin["financial_agent.py"]
        mkt["market_agent.py"]
        sen["sentiment_agent.py"]
        val["validator_agent.py"]
        deb["debate_agent.py"]
        med["mediator_agent.py"]
    end

    subgraph Utils["Utility Layer"]
        llm["llm.py"]
        prompts["prompts.py"]
        penalties["penalties.py"]
        confidence["confidence.py"]
        belief["belief.py"]
        parsing["parsing.py"]
    end

    subgraph Data["Data Layer"]
        onchain["onchain_data.py"]
        market["market_data.py"]
        sentiment["sentiment_data.py"]
        cache["outputs/cache/"]
    end

    subgraph RAG["RAG Layer (standalone)"]
        retriever["retriever.py"]
        chunking["chunking.py"]
        ingest["ingest_pdf.py"]
    end

    main --> fin & mkt & sen
    main --> val
    main --> med
    demo --> val
    demo --> med
    refresh --> fin & mkt & sen

    fin --> onchain
    fin --> llm
    fin --> prompts
    mkt --> market
    mkt --> llm
    mkt --> prompts
    sen --> sentiment
    sen --> llm
    sen --> prompts

    val --> deb
    val --> llm
    med --> penalties
    deb --> confidence

    onchain --> cache
    market --> cache
    sentiment --> cache
```
