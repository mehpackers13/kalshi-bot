"""
STRATEGY LAB — runs the same honest test on EVERY Kalshi category, every week.

For each recently settled, liquid market it records the volume-weighted trade price 3-36h before
close (the price a bot could actually have traded at) and whether YES won. It then asks, for every
category/series group x price bucket x side (buy YES / buy NO): after Kalshi's taker fee, did that
rule make money?  Results are clustered by event (ladders of strikes on one day are one outcome,
not ten), and a rule only PASSES if all of these hold:
    >= 30 independent events, mean net >= +1c/contract, 95% CI above 0,
    and positive in BOTH the older half and the newer half of the data.
Passing rules are written to data/lab_results.json. They go to forward paper testing next
(weather_tail.py is the first); real money is a separate human decision.

Cache: data/lab_cache.json grows each week, so the lab keeps learning from history, not just from
the few bets the bots place.

    python strategy_lab.py [--new 1200]      # fetch up to N new markets, then analyse
    python strategy_lab.py --analyse-only
"""
import argparse, collections, datetime, json, math, random, statistics, sys, time
import requests
import config

BASE = config.KALSHI_BASE_URL
CACHE = config.DATA_DIR / "lab_cache.json"
RESULTS = config.DATA_DIR / "lab_results.json"
REPORT = config.DATA_DIR / "LAB_REPORT.md"
CATEGORIES = ["Sports", "Crypto", "Financials", "Climate and Weather", "Economics", "Commodities", "Companies"]
SINCE_DAYS, MIN_VOL, PER_SERIES, MAX_SERIES_PER_CAT = 90, 200, 40, 60
BUCKETS = [(0.0, 0.10), (0.10, 0.30), (0.30, 0.70), (0.70, 0.90), (0.90, 1.0)]
S = requests.Session()


def get(path, params=None):
    for wait in (0, 2, 4):
        time.sleep(wait + 0.12)
        try:
            r = S.get(BASE + path, params=params, timeout=25)
        except Exception:
            return None
        if r.status_code == 200:
            return r.json()
        if r.status_code != 429:
            return None
    return None


def ts(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def fee(p):
    return math.ceil(0.07 * p * (1 - p) * 100) / 100


def event_of(ticker):
    return "-".join(ticker.split("-")[:2])


def load_cache():
    return json.loads(CACHE.read_text()) if CACHE.exists() else {}


def fetch_new(budget):
    cache = load_cache()
    since = int(time.time()) - SINCE_DAYS * 86400
    plan = []
    for cat in CATEGORIES:
        d = get("/series", {"category": cat}) or {}
        series = [x["ticker"] for x in d.get("series", []) if x.get("ticker")]
        random.Random(len(series)).shuffle(series)
        plan += [(cat, s) for s in series[:MAX_SERIES_PER_CAT]]
    have = collections.Counter(v["series"] for v in cache.values())
    plan.sort(key=lambda cs: have[cs[1]])                 # least-covered series first
    added = 0
    for cat, s in plan:
        if added >= budget:
            break
        d = get("/markets", {"status": "settled", "series_ticker": s, "min_close_ts": since, "limit": 200})
        mk = [m for m in (d or {}).get("markets", [])
              if m.get("result") in ("yes", "no") and float(m.get("volume_fp") or 0) >= MIN_VOL
              and m.get("close_time") and m["ticker"] not in cache]
        random.Random(7).shuffle(mk)
        got = 0
        for m in mk:
            if got >= PER_SERIES or added >= budget:
                break
            close = ts(m["close_time"])
            t = get("/markets/trades", {"ticker": m["ticker"], "min_ts": int(close - 36 * 3600),
                                        "max_ts": int(close - 3 * 3600), "limit": 1000}) or {}
            tr = t.get("trades", [])
            n = sum(float(x.get("count_fp") or x.get("count", 1)) for x in tr)
            if n < 20:
                continue
            px = sum(float(x.get("yes_price_dollars") or x["yes_price"] / 100) *
                     float(x.get("count_fp") or x.get("count", 1)) for x in tr) / n
            cache[m["ticker"]] = {"series": s, "cat": cat, "px": round(px, 4),
                                  "yes": 1 if m["result"] == "yes" else 0, "close": int(close)}
            got += 1
            added += 1
        if got:
            print(f"  {cat:20s} {s:22s} +{got}", flush=True)
    CACHE.write_text(json.dumps(cache))
    print(f"cache: +{added} new, {len(cache)} total")


def pnl(side, r):
    if side == "YES":
        return r["yes"] - r["px"] - fee(r["px"])
    return (1 - r["yes"]) - (1 - r["px"]) - fee(1 - r["px"])


def evaluate(rows, side):
    ev = collections.defaultdict(list)
    for tk, r in rows:
        ev[event_of(tk)].append(pnl(side, r))
    em = [statistics.mean(v) for v in ev.values()]
    if len(em) < 5:
        return None
    m = statistics.mean(em)
    se = statistics.stdev(em) / math.sqrt(len(em))
    return {"events": len(em), "trades": sum(len(v) for v in ev.values()),
            "net_c": round(m * 100, 2), "lo_c": round((m - 2 * se) * 100, 2), "hi_c": round((m + 2 * se) * 100, 2)}


def analyse():
    cache = load_cache()
    items = sorted(cache.items(), key=lambda kv: kv[1]["close"])
    mid = items[len(items) // 2][1]["close"] if items else 0
    groups = collections.defaultdict(list)
    for tk, r in items:
        groups[("category", r["cat"])].append((tk, r))
        groups[("series", r["series"])].append((tk, r))
    groups[("category", "ALL")] = items
    out, passed = [], []
    for (kind, name), rows in groups.items():
        for lo, hi in BUCKETS:
            b = [(tk, r) for tk, r in rows if lo <= r["px"] < hi + (0.0001 if hi == 1.0 else 0)]
            for side in ("YES", "NO"):
                e = evaluate(b, side)
                if not e:
                    continue
                old = evaluate([x for x in b if x[1]["close"] < mid], side)
                new = evaluate([x for x in b if x[1]["close"] >= mid], side)
                e.update(kind=kind, name=name, bucket=f"{lo:.0%}-{min(hi, 1):.0%}", side=side,
                         old_c=old["net_c"] if old else None, new_c=new["net_c"] if new else None)
                ok = (e["events"] >= 30 and e["net_c"] >= 1.0 and e["lo_c"] > 0
                      and old and new and old["net_c"] > 0 and new["net_c"] > 0)
                e["passed"] = bool(ok)
                out.append(e)
                if ok:
                    passed.append(e)
    out.sort(key=lambda e: -e["lo_c"])
    res = {"generated": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
           "markets": len(cache), "rules_tested": len(out), "passed": passed, "top_by_lower_bound": out[:25]}
    RESULTS.write_text(json.dumps(res, indent=1))
    lines = [f"# Strategy Lab — {res['generated']}", "",
             f"{len(cache)} settled markets, {len(out)} rules tested (group x price bucket x side, taker fees included).",
             f"**Rules passing the gate: {len(passed)}** (>=30 events, >=+1c, CI above 0, positive in both halves).", "",
             "| Rule | Events | Net c/contract | 95% range | Older half | Newer half | Pass |", "|---|---|---|---|---|---|---|"]
    for e in out[:25]:
        lines.append(f"| {e['kind']}:{e['name']} YES-price {e['bucket']} buy {e['side']} | {e['events']} | {e['net_c']:+.1f} | "
                     f"[{e['lo_c']:+.1f}, {e['hi_c']:+.1f}] | {e['old_c']} | {e['new_c']} | {'YES' if e['passed'] else ''} |")
    REPORT.write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:4]))
    for e in out[:12]:
        print(f"  {e['kind']}:{e['name'][:26]:26s} {e['bucket']:>8s} buy {e['side']:3s} events {e['events']:4d} net {e['net_c']:+5.1f}c "
              f"[{e['lo_c']:+.1f},{e['hi_c']:+.1f}] halves {e['old_c']}/{e['new_c']} {'PASS' if e['passed'] else ''}")
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--new", type=int, default=1200)
    ap.add_argument("--analyse-only", action="store_true")
    a = ap.parse_args()
    config.DATA_DIR.mkdir(exist_ok=True)
    if not a.analyse_only:
        fetch_new(a.new)
    analyse()
