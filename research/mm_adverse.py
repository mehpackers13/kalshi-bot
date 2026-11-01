"""Market-making feasibility (2026-10-31). Run from the repo root: python3 research/mm_probe.py then research/mm_adverse.py.
Result: spreads on liquid markets are ~1-2c; a maker filling every trade at the quote earned +0.40c/contract (5 min) and +0.19c (30 min) before fees, over 4,449 trades in 14 markets / 3 days. Thin edge, not income at small capital."""
import sys, json, time, statistics, bisect, collections
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
import requests, config
BASE = config.KALSHI_BASE_URL
S = requests.Session()
def get(path, params=None):
    for w in (0, 2, 4):
        time.sleep(w + 0.15)
        r = S.get(BASE + path, params=params, timeout=20)
        if r.status_code == 200: return r.json()
        if r.status_code != 429: return None
    return None
cand = json.load(open("research/mm_candidates.json"))
# liquid, real two-sided markets (skip junk books)
liquid = [c for c in cand if c["v24"] >= 5000 and c["spread"] <= 0.12]
print("liquid candidates:", len(liquid))
now = int(time.time()); start = now - 3 * 86400
HORIZONS = (5, 30)    # minutes
res = collections.defaultdict(list)   # horizon -> per-contract maker pnl
n_tr = 0
for c in liquid[:14]:
    t = c["t"]
    m = get(f"/markets/{t}")
    mk = (m or {}).get("market") or m or {}
    series = mk.get("series_ticker") or mk.get("event_ticker", t).split("-")[0]
    tr = []; cursor = None
    for _ in range(6):
        d = get("/markets/trades", {"ticker": t, "min_ts": start, "limit": 1000, **({"cursor": cursor} if cursor else {})})
        if not d: break
        tr += d.get("trades", []); cursor = d.get("cursor")
        if not cursor: break
    cd = get(f"/series/{series}/markets/{t}/candlesticks", {"start_ts": start, "end_ts": now, "period_interval": 1})
    cs = (cd or {}).get("candlesticks", [])
    if not tr or not cs: print(t[:30], "no data", len(tr), len(cs)); continue
    def mid_of(c):
        b = c.get("yes_bid", {}); a = c.get("yes_ask", {})
        try:
            bb = float(b.get("close_dollars") or b.get("close") / 100); aa = float(a.get("close_dollars") or a.get("close") / 100)
        except Exception: return None
        return (aa + bb) / 2 if aa > 0 and bb > 0 else None
    ts = [c["end_period_ts"] for c in cs]; mids = [mid_of(c) for c in cs]
    got = 0
    for x in tr:
        try:
            ct = int(__import__("datetime").datetime.fromisoformat(x["created_time"].replace("Z", "+00:00")).timestamp())
            px = float(x.get("yes_price_dollars") or x["yes_price"] / 100); n = float(x.get("count_fp") or x.get("count", 1))
        except Exception: continue
        i = bisect.bisect_left(ts, ct)
        if i >= len(ts) or mids[i] is None: continue
        mid0 = mids[i]
        taker_buys_yes = x.get("taker_side") == "yes"
        for h in HORIZONS:
            j = bisect.bisect_left(ts, ct + h * 60)
            if j >= len(ts) or mids[j] is None: continue
            # maker takes the other side of the taker: if taker buys YES at px, maker sold YES at px.
            pnl = (px - mids[j]) if taker_buys_yes else (mids[j] - px)
            res[h].append((pnl, n, px - mid0 if taker_buys_yes else mid0 - px))
        got += 1
    n_tr += got
    print(f"{t[:34]:34s} spread {c['spread']*100:.0f}c trades {len(tr):5d} used {got}")
print("trades used:", n_tr)
for h in HORIZONS:
    v = res[h]
    if not v: continue
    tot = sum(n for _, n, _ in v)
    avg = sum(p * n for p, n, _ in v) / tot
    half = sum(s * n for _, n, s in v) / tot      # spread captured vs mid at trade time
    print(f"horizon {h:>2}m: n={len(v)}, avg maker P&L {avg*100:+.2f}c/contract (captured vs mid {half*100:+.2f}c, "
          f"lost to price drift {(half-avg)*100:+.2f}c), win rate {sum(1 for p,_,_ in v if p>0)/len(v):.0%}")
