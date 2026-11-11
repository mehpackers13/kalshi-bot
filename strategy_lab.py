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

Entry prices are EXECUTABLE: the first hourly candlestick in the 36h->3h pre-close window with
volume > 0; buy-YES pays that candle's yes_ask close, buy-NO pays 1 - yes_bid close. Rows that have
no candle quote yet fall back to VWAP + 2c spread penalty ('vwap+2c') and can never make a rule PASS.
PASS also needs to survive an extra 1c of adverse selection. See docs/LAB_METHOD.md.

    python strategy_lab.py [--new 1200] [--requote 1500]   # fetch new, backfill quotes, analyse
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


HISTORY = config.DATA_DIR / "history.jsonl.gz"


def load_history():
    """Rows harvested by history_harvest.py (append-only gzipped JSONL, same row schema).
    Kept out of lab_cache.json because it is far larger and append-only."""
    rows = {}
    if not HISTORY.exists():
        return rows
    import gzip
    with gzip.open(HISTORY, "rt") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                rows[r.pop("t")] = r
            except Exception:
                continue        # tolerate a torn final line from an interrupted harvest
    return rows


def load_cache(merge_history=True):
    """Lab cache, merged with the harvested history. Harvested rows win on conflict: they
    always carry an executable candle quote, whereas older cache rows may be VWAP-only.
    Rows with no usable price are dropped — they would break bucketing in analyse()."""
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    if merge_history:
        cache.update(load_history())
    return {k: v for k, v in cache.items()
            if v.get("px") is not None or v.get("px_src") == "candle"}


def fetch_new(budget):
    cache = load_cache(merge_history=False)      # this function writes CACHE back
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
            row = {"series": s, "cat": cat, "px": round(px, 4),
                   "yes": 1 if m["result"] == "yes" else 0, "close": int(close)}
            q = candle_quote(s, m["ticker"], close)
            if q:
                row.update(q)
            cache[m["ticker"]] = row
            got += 1
            added += 1
        if got:
            print(f"  {cat:20s} {s:22s} +{got}", flush=True)
    CACHE.write_text(json.dumps(cache))
    print(f"cache: +{added} new, {len(cache)} total")


SPREAD_PENALTY = 0.02      # documented haircut when only a VWAP is known (px_src='vwap+2c')
ADVERSE_C = 1.0            # extra adverse selection assumed for the second PASS gate (cents)


def candle_quote(series, ticker, close):
    """First hourly candle in the 36h->3h pre-close window with volume > 0.
    Returns {'px_yes_ask','px_yes_bid','px_src':'candle'}, {'px_src':'nocandle'} if the market had
    no traded candle, or None on an API error (retry later)."""
    params = {"start_ts": int(close - 36 * 3600), "end_ts": int(close - 3 * 3600), "period_interval": 60}
    d = get(f"/series/{series}/markets/{ticker}/candlesticks", params)
    if not isinstance(d, dict):     # settled before the live cutoff -> archived endpoint (plain-number fields)
        d = get(f"/historical/markets/{ticker}/candlesticks", params)
    if not isinstance(d, dict):
        return None
    for c in sorted(d.get("candlesticks", []), key=lambda c: c.get("end_period_ts", 0)):
        try:
            if float(c.get("volume_fp") or c.get("volume") or 0) <= 0:
                continue
            ya, yb = c["yes_ask"], c["yes_bid"]
            ask = float(ya.get("close_dollars") or ya.get("close"))
            bid = float(yb.get("close_dollars") or yb.get("close"))
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        if 0 < ask <= 1 and 0 <= bid < 1 and bid <= ask:
            return {"px_yes_ask": round(ask, 4), "px_yes_bid": round(bid, 4), "px_src": "candle"}
    return {"px_src": "nocandle"}


def requote(budget):
    """Backfill executable quotes for up to `budget` cached markets, oldest first."""
    cache = load_cache(merge_history=False)      # this function writes CACHE back
    todo = sorted((k for k, v in cache.items() if "px_src" not in v and v.get("rq_fail", 0) < 2),
                  key=lambda k: cache[k]["close"])[:budget]
    ok = nocandle = fail = 0
    t0 = time.time()
    for i, tk in enumerate(todo, 1):
        r = cache[tk]
        q = candle_quote(r["series"], tk, r["close"])
        if q is None:
            r["rq_fail"] = r.get("rq_fail", 0) + 1
            fail += 1
        else:
            r.update(q)
            if q["px_src"] == "candle":
                ok += 1
            else:
                nocandle += 1
        if i % 100 == 0:
            CACHE.write_text(json.dumps(cache))
    CACHE.write_text(json.dumps(cache))
    left = sum(1 for v in cache.values() if "px_src" not in v)
    print(f"requote: {len(todo)} tried in {time.time() - t0:.0f}s -> {ok} candle, {nocandle} no traded candle, "
          f"{fail} errors; {left} still unquoted")


def exec_row(r):
    return r.get("px_src") == "candle"


def entry_cost(side, r):
    """Dollar cost of buying `side` at the lab entry."""
    if exec_row(r):
        return r["px_yes_ask"] if side == "YES" else 1 - r["px_yes_bid"]
    p = r["px"] if side == "YES" else 1 - r["px"]
    return min(0.99, p + SPREAD_PENALTY)


def yes_price(side, r):
    """YES-scale price used for bucketing: ask for YES, bid for NO (matches rules/lab_rules.py)."""
    if exec_row(r):
        return r["px_yes_ask"] if side == "YES" else r["px_yes_bid"]
    return r["px"]


def pnl(side, r):
    c = entry_cost(side, r)
    win = r["yes"] if side == "YES" else 1 - r["yes"]
    return win - c - fee(c)


def legacy_pnl(side, r):
    p = r["px"] if side == "YES" else 1 - r["px"]
    win = r["yes"] if side == "YES" else 1 - r["yes"]
    return win - p - fee(p)


def evaluate(rows, side, fn=None):
    fn = fn or pnl
    ev = collections.defaultdict(list)
    for tk, r in rows:
        ev[event_of(tk)].append(fn(side, r))
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
    n_exec_all = sum(1 for _, r in items if exec_row(r))
    groups = collections.defaultdict(list)
    for tk, r in items:
        groups[("category", r["cat"])].append((tk, r))
        groups[("series", r["series"])].append((tk, r))
    groups[("category", "ALL")] = items
    out, passed, legacy_passed = [], [], []
    for (kind, name), rows in groups.items():
        for lo, hi in BUCKETS:
            top = hi + (0.0001 if hi == 1.0 else 0)
            for side in ("YES", "NO"):
                # legacy (VWAP, no spread) verdict, kept only to show how much the old method overstated
                lb = [(tk, r) for tk, r in rows if lo <= r["px"] < top]
                le = evaluate(lb, side, legacy_pnl)
                lo_old = evaluate([x for x in lb if x[1]["close"] < mid], side, legacy_pnl)
                lo_new = evaluate([x for x in lb if x[1]["close"] >= mid], side, legacy_pnl)
                if (le and le["events"] >= 30 and le["net_c"] >= 1.0 and le["lo_c"] > 0
                        and lo_old and lo_new and lo_old["net_c"] > 0 and lo_new["net_c"] > 0):
                    legacy_passed.append((kind, name, f"{lo:.0%}-{min(hi, 1):.0%}", side))
                # executable evaluation
                b = [(tk, r) for tk, r in rows if lo <= yes_price(side, r) < top]
                bx = [x for x in b if exec_row(x[1])]
                n_exec, n_approx = len(bx), len(b) - len(bx)
                e = evaluate(bx, side)
                if not e:
                    continue
                old = evaluate([x for x in bx if x[1]["close"] < mid], side)
                new = evaluate([x for x in bx if x[1]["close"] >= mid], side)
                allx = evaluate(b, side)
                e.update(kind=kind, name=name, bucket=f"{lo:.0%}-{min(hi, 1):.0%}", lo=lo, hi=min(hi, 1.0),
                         side=side, n_exec=n_exec, n_approx=n_approx,
                         net_all_c=allx["net_c"] if allx else None,
                         old_c=old["net_c"] if old else None, new_c=new["net_c"] if new else None)
                gate1 = (e["events"] >= 30 and e["net_c"] >= 1.0 and e["lo_c"] > 0
                         and old and new and old["net_c"] > 0 and new["net_c"] > 0)
                gate2 = e["net_c"] - ADVERSE_C >= 0 and e["lo_c"] - ADVERSE_C > 0
                e["gate1"], e["gate2"] = bool(gate1), bool(gate2)
                e["passed"] = bool(gate1 and gate2)
                out.append(e)
                if e["passed"]:
                    e["paper_rule"] = f"lab:{kind}:{name}:{e['bucket']}:{side}"
                    e.update(min_vol=MIN_VOL, hours_min=6, hours_max=36)
                    passed.append(e)
    out.sort(key=lambda e: -e["lo_c"])
    res = {"generated": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
           "markets": len(cache), "markets_executable": n_exec_all, "rules_tested": len(out),
           "legacy_vwap_passes": len(legacy_passed), "passed": passed, "top_by_lower_bound": out[:25]}
    RESULTS.write_text(json.dumps(res, indent=1))
    lines = [f"# Strategy Lab — {res['generated']}", "",
             f"{len(cache)} settled markets ({n_exec_all} with executable candle quotes), {len(out)} rules tested "
             f"(group x YES-price bucket x side, taker fees included, entry = first traded hourly candle ask/bid).",
             f"**Rules passing both gates: {len(passed)}** (executable rows only; >=30 events, >=+1c, CI above 0, "
             f"positive in both halves, AND still positive after 1c extra adverse selection). "
             f"Old VWAP method would have passed {len(legacy_passed)}.",
             "These are in-sample candidates for paper testing, not proven edges.", "",
             "| Rule | Events | n_exec/n_approx | Net c | 95% range | Older | Newer | Net c -1c | Pass |",
             "|---|---|---|---|---|---|---|---|---|"]
    for e in out[:25]:
        lines.append(f"| {e['kind']}:{e['name']} YES-price {e['bucket']} buy {e['side']} | {e['events']} | "
                     f"{e['n_exec']}/{e['n_approx']} | {e['net_c']:+.1f} | [{e['lo_c']:+.1f}, {e['hi_c']:+.1f}] | "
                     f"{e['old_c']} | {e['new_c']} | {e['net_c'] - ADVERSE_C:+.1f} | {'YES' if e['passed'] else ''} |")
    REPORT.write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:5]))
    for e in out[:12]:
        print(f"  {e['kind']}:{e['name'][:26]:26s} {e['bucket']:>8s} buy {e['side']:3s} events {e['events']:4d} "
              f"exec/approx {e['n_exec']}/{e['n_approx']} net {e['net_c']:+5.1f}c [{e['lo_c']:+.1f},{e['hi_c']:+.1f}] "
              f"halves {e['old_c']}/{e['new_c']} {'PASS' if e['passed'] else ''}")
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--new", type=int, default=1200)
    ap.add_argument("--requote", type=int, default=0, help="backfill executable quotes for up to N cached markets")
    ap.add_argument("--analyse-only", action="store_true")
    a = ap.parse_args()
    config.DATA_DIR.mkdir(exist_ok=True)
    if not a.analyse_only:
        if a.new > 0:
            fetch_new(a.new)
        if a.requote > 0:
            requote(a.requote)
    analyse()
