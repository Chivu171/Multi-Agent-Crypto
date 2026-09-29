"""Rule baselines from CryptoTrade run_baseline.py, on the same environment.

Parameters are the upstream test choices (selected on their validation set):
SMA period 15, SLMA 15/30, Bollinger 20 x 2. Signal conventions, including the
upstream MACD direction, are kept as-is. LSTM and time-series models are not
reimplemented; cite the paper's numbers for those.
"""
from baselines.cryptotrade.env import TradingEnv, sharpe

BUY, SELL, FULL_BUY, FULL_SELL = 0.5, -0.5, 1, -1


def _signal_action(signal, state, need_cash=True):
    if signal == "buy" and (state["cash"] > 0 or not need_cash):
        return BUY
    if signal == "sell" and state["eth_held"] > 0:
        return SELL
    return 0


def decide(strategy, day, next_day, state):
    price = state["open"]
    if strategy == "buy_and_hold":
        return FULL_BUY if state["cash"] > 0 else 0
    if strategy == "optimal":  # oracle upper bound: knows tomorrow's open
        return FULL_BUY if price < next_day["open"] else FULL_SELL if price > next_day["open"] else 0
    if strategy == "SMA":
        sma = day["SMA_15"]
        return _signal_action("buy" if price > sma else "sell" if price < sma else "hold", state)
    if strategy == "SLMA":
        short, long = day["SMA_15"], day["SMA_30"]
        # upstream does not check cash for SLMA buys; the env ignores empty-cash buys anyway
        return _signal_action("buy" if short > long else "sell" if short < long else "hold", state, need_cash=False)
    if strategy == "MACD":
        signal = "buy" if day["MACD"] < day["Signal_Line"] else "sell" if day["MACD"] > day["Signal_Line"] else "hold"
        return _signal_action(signal, state)
    if strategy == "BollingerBands":
        upper = day["SMA_20"] + 2 * day["STD_20"]
        lower = day["SMA_20"] - 2 * day["STD_20"]
        return _signal_action("buy" if price < lower else "sell" if price > upper else "hold", state)
    raise ValueError(f"Unknown strategy {strategy}")


STRATEGIES = ("buy_and_hold", "SMA", "SLMA", "MACD", "BollingerBands", "optimal")


def run_rule(strategy, starting_date, ending_date):
    """Replicates run_strategy(): the daily return list starts with a 0 entry."""
    env = TradingEnv(starting_date, ending_date)
    state = env.reset()
    start, previous = state["net_worth"], state["net_worth"]
    returns, actions = [], []
    for i, day in enumerate(env.data):
        returns.append(state["net_worth"] / previous - 1)
        previous = state["net_worth"]
        if env.done:
            break
        action = decide(strategy, day, env.data[min(i + 1, len(env.data) - 1)], state)
        actions.append({"date": day["date"], "action": action})
        state, _ = env.step(action)
    return {"strategy": strategy, "total_return": state["net_worth"] / start - 1,
            "sharpe": sharpe(returns), "days": len(returns), "actions": actions}
