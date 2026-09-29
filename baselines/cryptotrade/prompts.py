"""Prompts from CryptoTrade env_history.py (commit 210da73), in two profiles.

- "code": verbatim released code — MACD only, 3-day reflection, "ETH" wording
  even for BTC.
- "paper": the method as written in the paper — MA crossover, MACD and
  Bollinger signals (Section 2.2, Figure 4; the code has them commented out),
  reflection over the previous week (Section 2.4), and the traded asset's name.
"""
DELIM = '\n"""\n'
ALL_SIGNALS = ("short_long_ma_signal", "macd_signal", "bollinger_bands_signal")
PROFILES = {
    "code": dict(signals=("macd_signal",), reflection_window=3, asset="ETH"),
    "paper": dict(signals=ALL_SIGNALS, reflection_window=7, asset="BTC"),
}


class History:
    """Chronological log of states, trader responses and actions."""

    def __init__(self, start_state, price_window=7, reflection_window=3, use_tech=True, use_txnstat=True,
                 signals=("macd_signal",), asset="ETH"):
        self.items = [{"label": "state", "value": start_state}]
        self.price_window, self.reflection_window = price_window, reflection_window
        self.use_tech, self.use_txnstat = use_tech, use_txnstat
        self.signals, self.asset = signals, asset

    def add(self, label, value):
        self.items.append({"label": label, "value": value})

    def prompts(self):
        a = self.asset  # only the fixed wording changes; news and model outputs stay verbatim
        an = "an" if a == "ETH" else "a"
        price_s = (f"You are {an} {a} cryptocurrency trading analyst. The recent price and auxiliary information "
                   "is given in chronological order below:" + DELIM)
        for item in self.items[-self.price_window * 3:]:
            if item["label"] == "state":
                state = item["value"]
                line = f'Open price: {state["open"]:.2f}'
                if self.use_txnstat:
                    for k, v in state["txnstat"].items():
                        line += f", {k}: {v}"
                if self.use_tech:
                    for k in self.signals:
                        line += f", {k}: {state['technical'][k]}"
                price_s += line + "\n"
        price_s += DELIM + ("Write one concise paragraph to analyze the recent information and estimate "
                            "the market trend accordingly.")

        state = self.items[-1]["value"]
        news_s = (f"You are {an} {a} cryptocurrency trading analyst. You are required to analyze the following "
                  f"news articles:{DELIM}{state['news']}{DELIM}Write one concise paragraph to analyze the news "
                  f"and estimate the market trend accordingly.")

        reflection_s = (f"You are {an} {a} cryptocurrency trading analyst. Your analysis and action history is "
                        "given in chronological order:" + DELIM)
        for item in self.items[-self.reflection_window * 3:]:
            if item["label"] == "trader_response":
                reflection_s += f'REASONING:\n{item["value"]}\n'
            elif item["label"] == "action":
                reflection_s += f'ACTION:\n{item["value"]}\n'
            elif item["label"] == "state":
                reflection_s += f'DAILY RETURN:\n{item["value"]["today_roi"]}\n'
        reflection_s += DELIM + (
            "Reflect on your recent performance and instruct your future trades from a high level, e.g., "
            "identify what information is currently more important, and what to be next, like aggresive or "
            "conversative. Write one concise paragraph to reflect on your recent trading performance with a "
            "focus on the effective strategies and information that led to the most successful outcomes, and "
            "the ineffective strategies and information that led to loss of profit. Identify key trends and "
            "indicators in the current cryptocurrency market that are likely to influence future trades. Also "
            "assess whether a more aggressive or conservative trading approach is warranted.")

        base = (f"You are an experienced {a} cryptocurrency trader and you are trying to maximize your overall "
                f"profit by trading {a}. In each day, you will make an action to buy or sell {a}. You are "
                "assisted by a few analysts below and need to decide the final action.")
        trader_s = (f"{base}\n\nON-CHAIN ANALYST REPORT:{DELIM}{{}}{DELIM}\nNEWS ANALYST REPORT:{DELIM}{{}}"
                    f"{DELIM}\nREFLECTION ANALYST REPORT:{DELIM}{{}}{DELIM}\n")
        trader_s += ("Now, start your response with your brief reasoning over the given reports. Then, based "
                     "on the synthesized reports, conclude a clear market trend, emphasizing long-term "
                     "strategies over short-term gains. Finally, indicate your trading action as a 1-decimal "
                     "float in the range of [-1,1], reflecting your confidence in the market trend and your "
                     "strategic decision to manage risk appropriately.")
        return price_s, news_s, reflection_s, trader_s
