"""Asset selection for the offline analysis scripts: ASSET=eth python scripts/<script>.py.

BTC (default) keeps every path unchanged; ETH reads outputs/baselines/cryptotrade/eth/
and writes each script's results under its own output folder in an eth/ subfolder.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from baselines.cryptotrade.env import set_asset  # noqa: E402

ASSET = os.environ.get("ASSET", "btc")
set_asset(ASSET)
RUNS = Path("outputs/baselines/cryptotrade") / ("" if ASSET == "btc" else ASSET)


def out_dir(base):
    return Path(base) if ASSET == "btc" else Path(base) / ASSET
