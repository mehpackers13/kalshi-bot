"""Favorite-longshot bias on Kalshi (2026-10-31). Run from repo root: python3 research/longshot_bias.py [cap_per_series]
For settled liquid markets in recurring series, take the volume-weighted trade price 3-36h before close as
the entry price, then compare price with how often YES actually won. Net of Kalshi taker fee; maker is fee-free."""
import sys, os, time, math, json, random, datetime, collections, statistics
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import requests, config
BASE = config.KALSHI_BASE_URL; S = requests.Session()
SERIES = {"sports": ["KXNFLGAME","KXNBAGAME","KXMLBGAME","KXNHLGAME","KXNCAAFGAME","KXEPLGAME"],
          "crypto_index": ["KXBTCD","KXBTC","KXETHD","KXINXU","KXINX","KXNASDAQ100U","KXNASDAQ100","KXXRPD"],
          "weather": ["KXHIGHNY","KXHIGHCHI","KXHIGHMIA","KXHIGHLAX","KXHIGHAUS"],
          "commodity_fx": ["KXWTI","KXUSDJPY"]}
CAP = int(sys.argv[1]) if len(sys.argv) > 1 else 80
def get(path, params):
    for w in (0, 2, 4):
        time.sleep(w + 0.12)
        r = S.get(BASE + path, params=params, timeout=25)
        if r.status_code == 200: return r.json()
        if r.status_code != 429: return None
    return None
def iso(s): return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
since = int(time.time()) - 90 * 86400
rows = []
for grp, lst in SERIES.items():
    for s in lst:
        mk, cur = [], None
        for _ in range(6):
            d = get("/markets", {"status": "settled", "series_ticker": s, "min_close_ts": since, "limit": 1000, **({"cursor": cur} if cur else {})})
            if not d: break
            mk += d["markets"]; cur = d.get("cursor")
            if not cur: break
        pool = [m for m in mk if m.get("result") in ("yes", "no") and float(m.get("volume_fp") or 0) >= 200 and m.get("close_time")]
        random.Random(7).shuffle(pool); got = 0
        for m in pool:
            if got >= CAP: break
            close = iso(m["close_time"])
            d = get("/markets/trades", {"ticker": m["ticker"], "min_ts": int(close - 36*3600), "max_ts": int(close - 3*3600), "limit": 1000})
            tr = (d or {}).get("trades", [])
            n = sum(float(t.get("count_fp") or t.get("count", 1)) for t in tr)
            if n < 20: continue
            px = sum(float(t.get("yes_price_dollars") or t["yes_price"]/100) * float(t.get("count_fp") or t.get("count", 1)) for t in tr) / n
            rows.append((grp, s, m["ticker"], px, 1 if m["result"] == "yes" else 0)); got += 1
        print(f"{s:14s} {got} markets", flush=True)
json.dump(rows, open("research/longshot_rows.json", "w"))
def fee(p): return math.ceil(0.07 * p * (1 - p) * 100) / 100
def table(rs, label):
    print(f"\n== {label}: {len(rs)} markets")
    print(f"{'YES price':>10} {'n':>5} {'avg px':>7} {'YES won':>8} | buy YES: gross / after fee | buy NO: gross / after fee   (cents per contract)")
    for lo, hi in [(0,.10),(.10,.30),(.30,.70),(.70,.90),(.90,1.01)]:
        b = [r for r in rs if lo <= r[3] < hi]
        if len(b) < 5: continue
        ap = statistics.mean(r[3] for r in b); wr = statistics.mean(r[4] for r in b)
        yg = statistics.mean(r[4]-r[3] for r in b); yf = statistics.mean(r[4]-r[3]-fee(r[3]) for r in b)
        ng = statistics.mean((1-r[4])-(1-r[3]) for r in b); nf = statistics.mean((1-r[4])-(1-r[3])-fee(1-r[3]) for r in b)
        print(f"{lo:>4.0%}-{min(hi,1):<4.0%} {len(b):5d} {ap:7.3f} {wr:8.3f} | {yg*100:+6.1f} / {yf*100:+6.1f}      | {ng*100:+6.1f} / {nf*100:+6.1f}")
table(rows, "ALL")
for g in SERIES: table([r for r in rows if r[0] == g], g)
