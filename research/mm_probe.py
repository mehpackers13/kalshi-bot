"""Market-making feasibility (2026-10-31). Run from the repo root: python3 research/mm_probe.py then research/mm_adverse.py.
Result: spreads on liquid markets are ~1-2c; a maker filling every trade at the quote earned +0.40c/contract (5 min) and +0.19c (30 min) before fees, over 4,449 trades in 14 markets / 3 days. Thin edge, not income at small capital."""
import sys, json, time, collections, statistics
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
import kalshi_api as k
api = k.KalshiAPI()
raw = api.get_all_open_markets()
def f(r, key):
    try: return float(r.get(key) or 0)
    except Exception: return 0.0
rows = []
for r in raw:
    bid = f(r, "yes_bid_dollars"); ask = f(r, "yes_ask_dollars"); v24 = f(r, "volume_24h_fp")
    if ask <= 0 or ask >= 1 or bid <= 0 or v24 <= 0: continue
    spread = ask - bid
    mid = (ask + bid) / 2
    rows.append(dict(t=r["ticker"], bid=bid, ask=ask, spread=spread, mid=mid, v24=v24, oi=f(r, "open_interest_fp"),
                     cat=r.get("category", "")))
print("markets with a two-sided quote and 24h volume:", len(rows))
for lo in (100, 1000, 10000, 100000):
    sub = [x for x in rows if x["v24"] >= lo]
    if sub:
        print(f"  24h vol >= {lo:>6} contracts: {len(sub):5d} markets, median spread {statistics.median(x['spread'] for x in sub)*100:.1f}c, "
              f"share with spread>=3c: {sum(1 for x in sub if x['spread']>=0.03)/len(sub):.0%}")
# theoretical gross: capture half-spread on a share of flow, mid-range prices only
cand = [x for x in rows if 0.10 <= x["mid"] <= 0.90 and x["v24"] >= 1000 and x["spread"] >= 0.02]
cand.sort(key=lambda x: -x["v24"] * x["spread"])
print("candidates (mid 10-90c, vol>=1000/day, spread>=2c):", len(cand))
for x in cand[:12]:
    print(f"  {x['t'][:34]:34s} bid {x['bid']:.2f} ask {x['ask']:.2f} spread {x['spread']*100:.0f}c vol24 {x['v24']:>10.0f} "
          f"gross/day if 1% of flow: ${x['v24']*0.01*x['spread']/2:,.2f}")
print("sum gross/day if 1% share of ALL candidates:", round(sum(x['v24']*0.01*x['spread']/2 for x in cand), 2))
json.dump(cand[:200], open("research/mm_candidates.json", "w"))
