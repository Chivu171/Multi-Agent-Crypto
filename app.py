"""Refresh outputs/logs.json — the cached specialist-agent output that main.py
falls back to when the LLM is unreachable. Run this standalone when you just
want to re-run the 3 specialist agents without the full validator/debate/
mediator pipeline. main.py is the canonical full-pipeline entry point.
"""

import json

from agents.financial_agent import run as financial_run
from agents.market_agent import run as market_run
from agents.sentiment_agent import run as sentiment_run

def main():
    agents = [
        ("Financial_Agent", financial_run),
        ("Market_Agent", market_run),
        ("Sentiment_Agent", sentiment_run),
    ]

    all_outputs = []
    for name, run_fn in agents:
        try:
            all_outputs.append(run_fn())
        except Exception as e:
            print(f"[!] {name} failed, skipping: {e}")

    print(json.dumps(all_outputs, indent=2, ensure_ascii=False))

    if all_outputs:
        with open("outputs/logs.json", "w", encoding="utf-8") as f:
            json.dump(all_outputs, f, indent=2, ensure_ascii=False)
    else:
        print("[!] All agents failed — outputs/logs.json left unchanged.")


if __name__ == "__main__":
    main()
