"""Demo 3 scenarios for Project 3 defense slides.

Scenarios:
    1. Consensus  — all 3 specialists agree (BUY/BUY/BUY)
    2. Conflict   — sharp disagreement (BUY/SELL/BUY)
    3. API error  — provider quota exhausted; the live pipeline stops with an
                    explicit status and never reuses old predictions

Outputs:
    outputs/demo_consensus.json
    outputs/demo_conflict.json
    outputs/demo_api_error.json
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from typing import List
from unittest.mock import patch

import httpx
import openai

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.conflict_analyzer import ConflictAnalyzer
from agents.debate_agent import DebateAgent
from agents.mediator_agent import run_mediator
from utils import llm
from utils.display import print_logic_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_output(
    agent_id: str,
    signal: str,
    confidence: float,
    entropy: float = 0.2,
    redundancy: float = 0.1,
    recency: float = 0.9,
    timestamp: str | None = None,
) -> dict:
    timestamp = timestamp or datetime.now().isoformat()
    direction_map = {"BUY": 1, "SELL": -1, "NEUTRAL": 0}
    return {
        "agent_id": agent_id,
        "signal": signal,
        "confidence": confidence,
        "belief_vector": {
            "direction": direction_map.get(signal, 0),
            "strength": confidence,
        },
        "evidence_chunks": [
            {
                "id": f"{agent_id.lower()}_chunk_0",
                "content": f"Mock evidence for {agent_id} — {signal} signal.",
                "metadata": {},
            }
        ],
        "logic_path": {
            "steps": [
                f"{agent_id} reasoning step 1",
                f"{agent_id} reasoning step 2",
            ]
        },
        "metadata": {
            "source_type": "demo_mock",
            "entropy": entropy,
            "redundancy_score": redundancy,
            "recency_weight": recency,
            "timestamp": timestamp,
        },
    }


def _run_pipeline(
    agents_output: List[dict],
    scenario_name: str,
    use_llm: bool = False,
) -> dict:
    """Run conflict analyzer → optional debate → mediator on mocked agent outputs."""
    print(f"\n{'=' * 60}")
    print(f"  SCENARIO: {scenario_name}")
    print(f"{'=' * 60}")

    # Step 1: Show inputs
    print("\n[Inputs] Specialist agent outputs:")
    for out in agents_output:
        print(
            f"  - {out['agent_id']}: {out['signal']} "
            f"(confidence={out['confidence']:.2f})"
        )

    # Step 2: Validate (includes conditional debate if use_llm=True and conflict high)
    analyzer = ConflictAnalyzer(alpha=0.6, threshold=0.4, use_llm=use_llm)
    validation_result = analyzer.evaluate_pipeline(agents_output)

    print("\n[Conflict Analyzer]")
    print(f"  conflict_score       : {validation_result['conflict_score']:.4f}")
    print(f"  mean_pairwise_kl     : {validation_result['metrics']['mean_pairwise_kl']:.4f}")
    print(f"  decision_variance    : {validation_result['metrics']['decision_variance']:.4f}")
    print(f"  conflict_detected    : {validation_result['conflict_detected']}")
    print(f"  conflict_categories  : {validation_result['conflict_categories']}")
    print(f"  trigger_debate_module: {validation_result['trigger_debate_module']}")

    # Step 3: Use debate outputs if the Conflict Analyzer triggered debate
    debate_outputs = validation_result.get("debate_updated_outputs")
    if debate_outputs:
        print("\n[Debate] Multi-round reconciliation completed (inside Conflict Analyzer).")
        final_outputs = debate_outputs
        for out in final_outputs:
            print(
                f"  - {out['agent_id']} final confidence: "
                f"{out['confidence']:.3f}"
            )
    else:
        final_outputs = agents_output
        print("\n[Debate] Skipped — conflict below threshold or use_llm=False.")

    # Step 4: Mediate
    mediator_result = run_mediator(final_outputs)
    score = mediator_result["S_final"]
    intensity = "STRONG" if abs(score) > 0.5 else "WEAK"
    signal = "BUY" if score > 0.05 else ("SELL" if score < -0.05 else "NEUTRAL")

    print("\n[Mediator]")
    print(f"  S_final  : {score:.4f}")
    print(f"  Intensity: {intensity}")
    print(f"  Signal   : {signal}")
    for d in mediator_result["details"]:
        print(
            f"    - {d['agent_id']}: weight={d['weight']:.4f}, "
            f"contribution={d['contribution']:.4f}"
        )

    # Step 5: RCA
    print("\n[RCA REPORT]")
    print("-" * 60)
    print(validation_result["root_cause_analysis"])
    print("-" * 60)

    return {
        "scenario": scenario_name,
        "timestamp": datetime.now().isoformat(),
        "inputs": agents_output,
        "validation": validation_result,
        "mediator_result": mediator_result,
        "final_signal": signal,
        "final_intensity": intensity,
    }


def _save(path: str, data: dict) -> None:
    os.makedirs("outputs", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\n[✓] Saved: {path}")


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

def scenario_consensus() -> dict:
    """All 3 agents agree BUY — expect low conflict, no debate."""
    agents_output = [
        _make_output("Financial_Agent", "BUY", 0.80, entropy=0.1, recency=0.9),
        _make_output("Market_Agent", "BUY", 0.75, entropy=0.1, recency=0.9),
        _make_output("Sentiment_Agent", "BUY", 0.70, entropy=0.15, recency=0.85),
    ]
    result = _run_pipeline(agents_output, "Consensus (3x BUY)", use_llm=False)
    _save("outputs/demo_consensus.json", result)
    return result


def scenario_conflict() -> dict:
    """Sharp disagreement BUY/SELL/BUY — expect high conflict, debate triggered."""
    agents_output = [
        _make_output(
            "Financial_Agent", "BUY", 0.85, entropy=0.1, redundancy=0.1, recency=0.9
        ),
        _make_output(
            "Market_Agent", "SELL", 0.75, entropy=0.3, redundancy=0.2, recency=0.95
        ),
        _make_output(
            "Sentiment_Agent", "BUY", 0.60, entropy=0.5, redundancy=0.4, recency=0.7
        ),
    ]
    result = _run_pipeline(agents_output, "Conflict (BUY/SELL/BUY)", use_llm=False)
    _save("outputs/demo_conflict.json", result)
    return result


def scenario_api_error() -> dict:
    """Quota exhausted — main.py stops with a reason instead of old predictions."""
    import main as live_pipeline

    print(f"\n{'=' * 60}")
    print("  SCENARIO: API error (OpenRouter free quota exhausted)")
    print(f"{'=' * 60}")

    # Only the provider call is simulated; data fetching and main.py run for real.
    quota = openai.RateLimitError(
        "Rate limit exceeded: free-models-per-day",
        response=httpx.Response(429, request=httpx.Request("POST", "https://openrouter.ai/api/v1")),
        body={"message": "Rate limit exceeded: free-models-per-day"},
    )
    status_path = "outputs/run_status.json"
    previous = open(status_path, encoding="utf-8").read() if os.path.exists(status_path) else None
    try:
        with patch.object(llm, "_send", side_effect=quota):
            live_pipeline.main()
        with open(status_path, encoding="utf-8") as f:
            run_status = json.load(f)
    finally:
        # Keep the real run's status file untouched by the demo.
        if previous is None:
            os.remove(status_path)
        else:
            with open(status_path, "w", encoding="utf-8") as f:
                f.write(previous)

    print("\n[Kết quả]")
    print(f"  status: {run_status['status']} ({run_status['reason']})")
    for error in run_status["errors"]:
        print(f"    - {error.get('agent', error.get('stage'))}: {error['status']} / {error['reason']}")
    print("  Không có tín hiệu nào được sinh ra; kết quả cũ trong outputs/ giữ nguyên.")
    result = {"scenario": "API error (quota exhausted → controlled stop)",
              "timestamp": datetime.now().isoformat(), "run_status": run_status}
    _save("outputs/demo_api_error.json", result)
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("  DEMO: 3 scenarios for Project 3 defense")
    print("=" * 60)

    scenario_consensus()
    scenario_conflict()
    scenario_api_error()

    print("\n" + "=" * 60)
    print("  ALL DEMOS COMPLETE")
    print("=" * 60)
    print("  Outputs:")
    print("    - outputs/demo_consensus.json")
    print("    - outputs/demo_conflict.json")
    print("    - outputs/demo_api_error.json")


if __name__ == "__main__":
    main()
