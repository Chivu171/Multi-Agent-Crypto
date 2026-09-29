"""Run the CryptoTrade baseline on the paper's BTC windows.

Rule baselines (no LLM, free):
    python -m baselines.cryptotrade.run rules --window bull
LLM agent (paid, cached; rerun the same command to resume):
    python -m baselines.cryptotrade.run agent --window bull --variant market_only
Outputs go to outputs/baselines/cryptotrade/<window>/.
"""
import argparse
import json
from pathlib import Path

from baselines.cryptotrade.agent import VARIANTS, CachedLLM, run_agent
from baselines.cryptotrade.env import WINDOWS, TradingEnv
from baselines.cryptotrade.rules import STRATEGIES, run_rule

OUT = Path("outputs/baselines/cryptotrade")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=("rules", "agent"))
    parser.add_argument("--window", choices=sorted(WINDOWS), required=True)
    parser.add_argument("--variant", choices=sorted(VARIANTS), default="full")
    parser.add_argument("--model", help="Default: $CRYPTOTRADE_MODEL or openai/gpt-4o")
    args = parser.parse_args()
    start, end = WINDOWS[args.window]
    out = OUT / args.window
    out.mkdir(parents=True, exist_ok=True)

    if args.mode == "rules":
        results = [run_rule(s, start, end) for s in STRATEGIES]
        (out / "rules.json").write_text(json.dumps(results, indent=2))
        print(f"{args.window} {start}..{end}")
        for r in results:
            print(f"  {r['strategy']:15s} return {r['total_return'] * 100:7.2f}%  sharpe {r['sharpe']:.2f}")
        return

    days = TradingEnv(start, end).total_steps - 1
    per_day = 2 + VARIANTS[args.variant]["use_news"] + VARIANTS[args.variant]["use_reflection"]
    ask = CachedLLM(OUT / "calls", model=args.model)
    print(f"{args.variant} on {args.window}: {days} trading days x {per_day} calls = {days * per_day} "
          f"calls (cached ones are free); model {ask.model}", flush=True)
    result = run_agent(start, end, ask, args.variant, out_dir=out / f"agent_{args.variant}")
    result.update(model=ask.model, new_calls=ask.new_calls, cached_calls=ask.cached_calls, usage=ask.usage)
    (out / f"agent_{args.variant}" / "result.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
