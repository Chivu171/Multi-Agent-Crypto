"""BTC trading environment reimplemented from CryptoTrade (Li et al., EMNLP 2024).

Mirrors eth_env.py of github.com/Xtra-Computing/CryptoTrade (commit 210da73):
- starts with 1,000,000 split 50/50 between cash and BTC at the first open;
- one action per day in [-1, 1]: >0 spends that fraction of cash, <0 sells that
  fraction of holdings, at the day's open; long-only;
- each trade pays EX_RATE of its value plus a fixed "gas" of GAS_FEE coins
  valued at the open (the original applies the ETH gas constant to BTC too);
- net worth is marked at the next day's open.
Indicators are computed on open prices over the full history, as upstream.
"""
import csv
import datetime as dt
import json
import re
from pathlib import Path

import numpy as np

DATA_DIR = Path(__file__).parent / "data"
STARTING_NET_WORTH = 1_000_000
STARTING_CASH_RATIO = 0.5
GAS_FEE = 21000 * 70 * 1e-9  # coins per trade
EX_RATE = 4e-3
SMA_PERIODS = (5, 10, 15, 20, 30)
WINDOWS = {  # BTC test periods from the paper (Table 1)
    "bear": ("2023-04-12", "2023-06-16"),
    "sideways": ("2023-06-17", "2023-08-25"),
    "bull": ("2023-10-01", "2023-12-01"),
}
ACTION_PATTERN = re.compile(r"-?(?:0(?:\.\d{1})|1\.0)")


def _ewm(values, span):
    alpha = 2 / (span + 1)
    out = np.empty(len(values))
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return out


def load_prices(data_dir=DATA_DIR):
    """Daily rows sorted by date with SMA/STD/MACD computed on open prices."""
    with open(data_dir / "bitcoin_daily_price.csv", newline="") as f:
        rows = sorted(csv.DictReader(f), key=lambda r: r["timeOpen"])
    opens = np.array([float(r["open"]) for r in rows])
    days = []
    for i, r in enumerate(rows):
        day = {"date": r["timeOpen"][:10], "time_open": r["timeOpen"], "open": opens[i]}
        for p in SMA_PERIODS:
            window = opens[max(0, i - p + 1): i + 1]
            full = len(window) == p
            day[f"SMA_{p}"] = float(window.mean()) if full else float("nan")
            # pandas rolling std uses ddof=1
            day[f"STD_{p}"] = float(window.std(ddof=1)) if full else float("nan")
        days.append(day)
    macd = _ewm(opens, 12) - _ewm(opens, 26)
    signal = _ewm(macd, 9)
    for day, m, s in zip(days, macd, signal):
        day["MACD"], day["Signal_Line"] = float(m), float(s)
    return days


def _number(text):
    # Printed like the pandas values upstream: integers without ".0", floats by repr.
    return int(text) if text.lstrip("-").isdigit() else float(text)


def load_txn_stats(data_dir=DATA_DIR):
    """Columns keep CSV order. Upstream iterates a set(), so its prompt order
    changes between Python processes; a fixed order keeps runs reproducible."""
    with open(data_dir / "bitcoin_transaction_statistics.csv", newline="") as f:
        return {r["day"][:10]: {k: _number(v) for k, v in r.items() if k != "day"} for r in csv.DictReader(f)}


def load_news(date, data_dir=DATA_DIR):
    path = data_dir / "selected_bitcoin_202301_202401" / f"{date}.json"
    if not path.exists():
        return "N/A"
    news, seen = [], set()
    for item in json.loads(path.read_text()):
        if item["title"] in seen:
            continue
        seen.add(item["title"])
        entry = {k: item[k] for k in ("id", "time", "title", "content")}
        if len(entry["content"]) > 5000:
            entry["content"] = entry["content"][:5000] + "..."
        news.append(entry)
    return news


def macd_signal(day):
    # Upstream convention (kept for fidelity): MACD below its signal line = buy.
    if day["MACD"] < day["Signal_Line"]:
        return "buy"
    if day["MACD"] > day["Signal_Line"]:
        return "sell"
    return "hold"


def slma_signal(day):
    # Upstream eth_env.py (commented out there): SMA15 above SMA20 = sell.
    if day["SMA_15"] > day["SMA_20"]:
        return "sell"
    if day["SMA_15"] < day["SMA_20"]:
        return "buy"
    return "hold"


def bollinger_signal(day, price):
    upper = day["SMA_20"] + 2 * day["STD_20"]
    lower = day["SMA_20"] - 2 * day["STD_20"]
    if price < lower:
        return "buy"
    if price > upper:
        return "sell"
    return "hold"


def parse_action(action):
    """Upstream parsing: the last 1-decimal number in [-1, 1]; otherwise 0."""
    if isinstance(action, str):
        found = ACTION_PATTERN.findall(action)
        action = float(found[-1]) if found else 0.0
    return action if -1 <= action <= 1 else 0.0


class TradingEnv:
    def __init__(self, starting_date, ending_date, data_dir=DATA_DIR):
        self.data = [d for d in load_prices(data_dir) if starting_date <= d["date"] <= ending_date]
        if len(self.data) < 2:
            raise ValueError("Window needs at least two days")
        self.txn_stats = load_txn_stats(data_dir)
        self.data_dir = data_dir
        self.total_steps = len(self.data)

    def _close_state(self, today, next_day, first_day=False):
        next_open = next_day["open"]
        net_worth = self.cash + self.coin_held * next_open
        roi = net_worth / STARTING_NET_WORTH - 1
        today_roi = net_worth / self.last_net_worth - 1
        self.last_net_worth = net_worth
        date = dt.date.fromisoformat(today["date"])
        if first_day:
            date -= dt.timedelta(days=1)
        key = date.isoformat()
        txn = self.txn_stats.get(key) or {k: "N/A" for k in next(iter(self.txn_stats.values()))}
        return {
            "cash": self.cash, "eth_held": self.coin_held, "open": next_open,
            "net_worth": net_worth, "roi": roi, "today_roi": today_roi,
            # All three upstream signals; the prompt profile decides which are shown.
            "technical": {"short_long_ma_signal": slma_signal(next_day),
                          "macd_signal": macd_signal(next_day),
                          "bollinger_bands_signal": bollinger_signal(next_day, next_open)},
            "txnstat": txn, "news": load_news(key, self.data_dir), "date": today["time_open"],
        }

    def reset(self):
        self.current_step = 0
        today = self.data[0]
        self.starting_price = today["open"]
        self.cash = STARTING_NET_WORTH * STARTING_CASH_RATIO
        self.coin_held = (STARTING_NET_WORTH - self.cash) / self.starting_price
        self.last_net_worth = STARTING_NET_WORTH
        self.done = False
        self.last_state = self._close_state(today, today, first_day=True)
        return self.last_state

    def step(self, raw_action):
        action = parse_action(raw_action)
        today, next_day = self.data[self.current_step], self.data[self.current_step + 1]
        price = today["open"]
        if action < 0 and self.coin_held > 0:
            coin_diff = -action * self.coin_held
            cash_diff = coin_diff * price
            self.coin_held -= coin_diff
            # Same operation order as upstream, so floating-point results match exactly.
            self.cash += cash_diff
            self.cash -= GAS_FEE * price + cash_diff * EX_RATE
        if action > 0 and self.cash > 0:
            cash_diff = action * self.cash
            self.cash -= cash_diff
            self.coin_held += cash_diff / price
            self.cash -= GAS_FEE * price + cash_diff * EX_RATE
        self.current_step += 1
        self.done = self.current_step >= self.total_steps - 1
        state = self._close_state(today, next_day)
        self.last_state = state
        return state, {"raw_action": raw_action, "actual_action": action, "today": today["date"]}


def sharpe(returns):
    """Upstream definition: mean / std of daily returns in %, risk-free 0, population std."""
    r = np.array(returns) * 100
    return float(r.mean() / r.std()) if r.std() > 0 else None
