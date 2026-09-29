"""Check this reimplementation against the original CryptoTrade code.

Needs a clone of github.com/Xtra-Computing/CryptoTrade (commit 210da73) and an
environment with pandas (not a project dependency):
    python baselines/cryptotrade/verify_against_upstream.py <CryptoTrade dir> <this repo dir>
Compares all rule baselines on the three BTC windows and the four agent prompts
over 12 steps. Upstream lists on-chain fields from a set() (order changes per
process) and parses floats with pandas, so fields are compared unordered and to
10 significant digits.
"""
import sys, re, json, ast
from argparse import Namespace
UP = sys.argv[1]; OURS = sys.argv[2]
sys.path.insert(0, UP)
import os; os.chdir(UP)
import numpy as np, pandas as pd
import eth_env
from env_history import EnvironmentHistory
# upstream run_strategy, executed against a BTC dataframe and env
src = open("run_baseline.py").read()
tree = ast.parse(src)
fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run_strategy")
code = ast.get_source_segment(src, fn).replace("print(result_str)", "return result")
df = pd.read_csv("data/bitcoin_daily_price.csv"); df = df.sort_values("timeOpen")
df["date"] = pd.to_datetime(df["timeOpen"], format="%Y-%m-%dT%H:%M:%S.%fZ")
for p in [5,10,15,20,30]:
    df[f"SMA_{p}"] = df["open"].rolling(window=p).mean(); df[f"STD_{p}"] = df["open"].rolling(window=p).std()
df["EMA_12"] = df["open"].ewm(span=12, adjust=False).mean(); df["EMA_26"] = df["open"].ewm(span=26, adjust=False).mean()
df["MACD"] = df["EMA_12"] - df["EMA_26"]; df["Signal_Line"] = df["MACD"].ewm(span=9, adjust=False).mean()
class BTCEnv(eth_env.ETHTradingEnv):
    def __init__(self, args): super().__init__(Namespace(dataset="btc", **vars(args)))
g = {"ETHTradingEnv": BTCEnv, "Namespace": Namespace, "df": df, "np": np, "BUY": .5, "SELL": -.5, "FULL_BUY": 1, "FULL_SELL": -1}
exec(code, g)
sys.path.insert(0, OURS); os.chdir(OURS)
from baselines.cryptotrade.rules import run_rule
from baselines.cryptotrade.env import WINDOWS, TradingEnv
from baselines.cryptotrade.prompts import History
worst = 0
for w, (a, b) in WINDOWS.items():
    for s, sargs in [("buy_and_hold", {}), ("SMA", {"period": 15}), ("SLMA", {"short": "SMA_15", "long": "SMA_30"}),
                     ("MACD", {}), ("BollingerBands", {"period": 20, "multiplier": 2}), ("optimal", {})]:
        os.chdir(UP); up = g["run_strategy"](s, {"starting_date": a, "ending_date": b, **sargs}); os.chdir(OURS)
        me = run_rule(s, a, b)
        d = max(abs(up["total_irr"] - me["total_return"]), abs(up["sharp_ratio"] - me["sharpe"]))
        worst = max(worst, d)
        print(f"{w:8s} {s:15s} upstream {up['total_irr']*100:8.3f}% {up['sharp_ratio']:6.3f} | ours {me['total_return']*100:8.3f}% {me['sharpe']:6.3f}")
# prompts: same fake trader responses; txn fields compared as an unordered set, numbers to 12 significant digits
def norm(p):
    out=[]
    for line in p.splitlines():
        if line.startswith("Open price:"):
            parts=line.split(", ")
            def f(x):
                k,_,v=x.partition(": ")
                try: v=f"{float(v):.10g}"
                except ValueError: pass
                return k+": "+v
            line=", ".join([f(parts[0])]+sorted(f(x) for x in parts[1:]))
        out.append(line)
    return "\n".join(out)
os.chdir(UP)
up_env = eth_env.ETHTradingEnv(Namespace(dataset="btc", starting_date="2023-10-01", ending_date="2023-10-20"))
s0, *_ = up_env.reset()
args = Namespace(price_window=7, reflection_window=3, use_tech=1, use_txnstat=1)
uh = EnvironmentHistory("", s0, [], [], args)
os.chdir(OURS)
my_env = TradingEnv("2023-10-01", "2023-10-20"); m0 = my_env.reset(); mh = History(m0)
mismatch = 0
for step in range(12):
    os.chdir(UP); up_prompts = uh.get_prompt(); os.chdir(OURS)
    my_prompts = mh.prompts()
    for idx,(x,y) in enumerate(zip(up_prompts, my_prompts)):
        if norm(x)!=norm(y):
            mismatch+=1

    resp = f"reasoning ... action {[0.3,-0.5,1.0,-1.0,0.0][step % 5]:.1f}"
    os.chdir(UP); us, *_rest = up_env.step(resp); os.chdir(OURS)
    ms, info = my_env.step(resp)
    for h, st in ((uh, us), (mh, ms)):
        h.add("trader_response", resp); h.add("action", f"{info['actual_action']:.1f}"); h.add("state", st)
print("prompt mismatches over 12 steps x 4 prompts:", mismatch)
print("max |diff| return/sharpe:", worst)
sys.exit(1 if mismatch or worst > 1e-12 else 0)
