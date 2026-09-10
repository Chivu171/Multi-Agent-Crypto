"""Refresh outputs/logs.json — re-run the 3 specialist agents without
the full validator/debate/mediator pipeline. Useful for pre-warming the
fallback cache that main.py uses when the LLM is unreachable.

Usage:
    python scripts/refresh_logs.py
"""

from __future__ import annotations

import json
import os
import sys
from typing import List, Dict, Any

# Ensure repo root is on sys.path when run as a script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.financial_agent import run as financial_run
from agents.market_agent import run as market_run
from agents.sentiment_agent import run as sentiment_run


def refresh_logs(output_path: str = "outputs/logs.json") -> List[Dict[str, Any]]:
    """Run the 3 specialist agents and persist their outputs to ``output_path``.

    Returns the list of agent outputs, possibly empty if all agents failed.
    """
    agents = [
        ("Financial_Agent", financial_run),
        ("Market_Agent", market_run),
        ("Sentiment_Agent", sentiment_run),
    ]

    all_outputs: List[Dict[str, Any]] = []
    for name, run_fn in agents:
        try:
            all_outputs.append(run_fn())
        except Exception as e:
            print(f"[!] {name} failed, skipping: {e}")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    if all_outputs:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(all_outputs, f, indent=2, ensure_ascii=False)
        print(f"[✓] {len(all_outputs)} agent outputs saved to {output_path}")
    else:
        print("[!] All agents failed — logs.json left unchanged.")

    return all_outputs


def main() -> None:
    refresh_logs()


if __name__ == "__main__":
    main()
