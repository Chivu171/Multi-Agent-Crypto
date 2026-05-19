from agents.financial_agent import run as financial_run
from agents.market_agent import run as market_run
from agents.sentiment_agent import run as sentiment_run

import json


financial = financial_run()

market = market_run()

sentiment = sentiment_run()


all_outputs = [
    financial,
    market,
    sentiment
]


print(json.dumps(all_outputs, indent=2))


with open("outputs/logs.json", "w", encoding="utf-8") as f:
    json.dump(
        all_outputs,
        f,
        indent=2,
        ensure_ascii=False
    )