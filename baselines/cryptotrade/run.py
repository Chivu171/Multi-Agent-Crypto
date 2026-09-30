"""Run the CryptoTrade baseline on the paper's BTC windows.

Rule baselines (no LLM, free):
    python -m baselines.cryptotrade.run rules --window bull
LLM agent (cached; rerun the same command to resume):
    python -m baselines.cryptotrade.run agent --window bull --variant market_only
Our multi-agent system in the same environment (LLM_BACKEND/LMSTUDIO_MODEL select the model):
    python -m baselines.cryptotrade.run ours --window bull
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
    parser.add_argument("mode", choices=("rules", "agent", "ours"))
    parser.add_argument("--window", choices=sorted(WINDOWS), required=True)
    parser.add_argument("--variant", choices=sorted(VARIANTS), default="full")
    parser.add_argument("--profile", choices=("paper", "code"), default="paper",
                        help="paper = method as described in the paper (default); code = released code")
    parser.add_argument("--model", help="Default: $CRYPTOTRADE_MODEL or openai/gpt-4o")
    parser.add_argument("--threshold", type=float, help="ours: Conflict Analyzer threshold (default 0.4)")
    parser.add_argument("--day-budget", type=float, default=900, help="ours: seconds per trading day")
    parser.add_argument("--limit-days", type=int, help="ours: only the first N trading days (pilot)")
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

    if args.mode == "ours":
        from baselines.cryptotrade.ours import run_window
        from utils.config import get_agent_config
        from utils.thresholds import DEFAULT_CONFLICT_THRESHOLD
        model = get_agent_config("market")["model"].replace("/", "_")
        threshold = DEFAULT_CONFLICT_THRESHOLD if args.threshold is None else args.threshold
        suffix = "" if threshold == DEFAULT_CONFLICT_THRESHOLD else f"_t{threshold:g}"
        summary = run_window((start, end), out / f"ours{suffix}__{model}", threshold, args.day_budget,
                             args.limit_days, log=lambda m: print(m, flush=True))
        print(json.dumps({k: summary[k] for k in ("status_counts", "debate_days", "explanation_rejected_days",
                                                   "results")}, indent=2))
        return

    days = TradingEnv(start, end).total_steps - 1
    per_day = 2 + VARIANTS[args.variant]["use_news"] + VARIANTS[args.variant]["use_reflection"]
    ask = CachedLLM(OUT / "calls", model=args.model)
    print(f"{args.profile}/{args.variant} on {args.window}: {days} trading days x {per_day} calls = {days * per_day} "
          f"calls (cached ones are free); model {ask.model}", flush=True)
    # The model is part of the path so runs with different models never overwrite each other.
    run_dir = out / f"agent_{args.profile}_{args.variant}__{ask.model.replace('/', '_')}"
    result = run_agent(start, end, ask, args.variant, out_dir=run_dir, profile=args.profile)
    result.update(model=ask.model, reasoning_effort=ask.reasoning_effort,
                  new_calls=ask.new_calls, cached_calls=ask.cached_calls, usage=ask.usage)
    (run_dir / "result.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
