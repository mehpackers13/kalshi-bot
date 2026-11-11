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
    try:
        with gzip.open(HISTORY, "rt") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                    rows[r.pop("t")] = r
                except Exception:
                    continue            # a single malformed row
    except (EOFError, OSError, gzip.BadGzipFile) as exc:
        # The harvester appends, so an interrupted run leaves a torn final gzip member.
        # EOFError comes from the line ITERATOR, so it must be caught around the loop;
        # catching per line would make the whole harvested history unreadable.
        print(f"warn: {HISTORY.name} truncated ({type(exc).__name__}); "
              f"analysing the {len(rows)} rows read before the tear")
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
    sd = statistics.stdev(em)
    se = sd / math.sqrt(len(em))
    # Two-sided p-value for mean > 0, normal approximation. Fine at the >=30 events the
    # PASS gate requires; only used for the relative FDR ranking, never as the sole gate.
    if se > 0:
        t = m / se
        p = 2 * (1 - statistics.NormalDist().cdf(abs(t)))
    else:
        t, p = (float("inf") if m > 0 else 0.0), (0.0 if m > 0 else 1.0)
    return {"events": len(em), "trades": sum(len(v) for v in ev.values()),
            "net_c": round(m * 100, 2), "lo_c": round((m - 2 * se) * 100, 2),
            "hi_c": round((m + 2 * se) * 100, 2), "t": round(t, 3), "p": p}


FDR_Q = 0.10        # Benjamini-Hochberg target false-discovery rate across all tested rules
HOLDOUT_FRAC = 0.30  # newest share of history held out of discovery entirely


def bh_threshold(pvals, q=FDR_Q):
    """Largest Benjamini-Hochberg cutoff controlling FDR at q over m simultaneous tests.

    The lab tests ~500 rules at once. At a flat 95% CI roughly 1 in 20 clears by chance,
    so a few dozen 'edges' would be pure noise -- and a bigger history produces MORE of
    them, not fewer. BH keeps the expected share of false passes among passes at <= q.
    Returns 0.0 when nothing survives (i.e. pass nothing)."""
    m = len(pvals)
    if not m:
        return 0.0
    ordered = sorted(pvals)
    thr = 0.0
    for i, p in enumerate(ordered, start=1):
        if p <= q * i / m:
            thr = p
    return thr


def analyse():
    cache = load_cache()
    items = sorted(cache.items(), key=lambda kv: kv[1]["close"])
    n_exec_all = sum(1 for _, r in items if exec_row(r))
    # True out-of-sample holdout: the newest HOLDOUT_FRAC of history is excluded from
    # discovery entirely. gate1's older/newer split is in-sample on both sides, so it
    # cannot catch a rule that was selected by looking at the whole period.
    cut_i = int(len(items) * (1 - HOLDOUT_FRAC))
    cut_ts = items[cut_i][1]["close"] if items else 0
    insample = items[:cut_i]
    holdout = items[cut_i:]
    # older/newer halves must split WITHIN the in-sample period; using the midpoint of all
    # history would put the whole "newer" half inside the holdout, leaving it always empty
    mid = insample[len(insample) // 2][1]["close"] if insample else 0
    groups = collections.defaultdict(list)
    for tk, r in insample:
        groups[("category", r["cat"])].append((tk, r))
        groups[("series", r["series"])].append((tk, r))
    groups[("category", "ALL")] = insample
    hgroups = collections.defaultdict(list)
    for tk, r in holdout:
        hgroups[("category", r["cat"])].append((tk, r))
        hgroups[("series", r["series"])].append((tk, r))
    hgroups[("category", "ALL")] = holdout
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
                # out-of-sample confirmation on the held-out newest slice
                hrows = [(tk, r) for tk, r in hgroups.get((kind, name), [])
                         if lo <= yes_price(side, r) < top and exec_row(r)]
                h = evaluate(hrows, side)
                e["hold_events"] = h["events"] if h else 0
                e["hold_c"] = h["net_c"] if h else None
                gate1 = (e["events"] >= 30 and e["net_c"] >= 1.0 and e["lo_c"] > 0
                         and old and new and old["net_c"] > 0 and new["net_c"] > 0)
                gate2 = e["net_c"] - ADVERSE_C >= 0 and e["lo_c"] - ADVERSE_C > 0
                # gate4: must still be profitable on data never used to pick it
                gate4 = bool(h and h["events"] >= 10 and h["net_c"] >= 1.0)
                e["gate1"], e["gate2"], e["gate4"] = bool(gate1), bool(gate2), gate4
                out.append(e)

    # gate3: Benjamini-Hochberg across every rule tested in this run, applied only to
    # rules that already cleared the economic gates, so the correction is not diluted.
    cands = [e for e in out if e["gate1"] and e["gate2"] and e["gate4"]]
    thr = bh_threshold([e["p"] for e in out], FDR_Q)
    for e in out:
        e["bh_thresh"] = round(thr, 6)
        e["gate3"] = bool(e["p"] <= thr) if thr > 0 else False
        e["passed"] = bool(e["gate1"] and e["gate2"] and e["gate3"] and e["gate4"])
        if e["passed"]:
            e["paper_rule"] = f"lab:{e['kind']}:{e['name']}:{e['bucket']}:{e['side']}"
            e.update(min_vol=MIN_VOL, hours_min=6, hours_max=36)
            passed.append(e)
    out.sort(key=lambda e: -e["lo_c"])
    res = {"generated": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
           "markets": len(cache), "markets_executable": n_exec_all, "rules_tested": len(out),
           "insample_markets": len(insample), "holdout_markets": len(holdout),
           "holdout_from": int(cut_ts), "fdr_q": FDR_Q, "bh_threshold": round(thr, 6),
           "economic_candidates": len(cands),
           "legacy_vwap_passes": len(legacy_passed), "passed": passed, "top_by_lower_bound": out[:25]}
    RESULTS.write_text(json.dumps(res, indent=1))
    lines = [f"# Strategy Lab — {res['generated']}", "",
             f"{len(cache)} settled markets ({n_exec_all} with executable candle quotes), {len(out)} rules tested "
             f"(group x YES-price bucket x side, taker fees included, entry = first traded hourly candle ask/bid).",
             f"Discovery used the oldest {len(insample)} markets; the newest {len(holdout)} were held out "
             f"and never used to pick a rule.", "",
             f"**Rules passing all four gates: {len(passed)}.** A rule must clear:", "",
             "1. **economic** — >=30 events, >=+1c/contract, 95% CI above 0, positive in both halves;",
             "2. **adverse selection** — still positive after 1c extra slippage;",
             f"3. **multiple comparisons** — Benjamini-Hochberg at q={FDR_Q:.2f} over all {len(out)} rules "
             f"tested together (cutoff p<={thr:.5f}). Without this, ~1 rule in 20 clears a 95% CI by pure "
             f"chance, so a larger history yields MORE fake edges, not fewer;",
             "4. **out of sample** — >=10 events in the held-out newest slice and >=+1c there too.", "",
             f"{len(cands)} rules cleared gates 1, 2 and 4; {len(passed)} of those survived the FDR correction. "
             f"The old VWAP method, with no fees, spread, FDR or holdout, would have passed {len(legacy_passed)}.",
             "A pass is a candidate for forward paper testing, not a proven edge, and never a live bet.", "",
             "| Rule | Events | Net c | 95% range | Older | Newer | Holdout (n) | p | Gates 1/2/3/4 | Pass |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for e in out[:25]:
        g = "".join("Y" if e.get(f"gate{i}") else "·" for i in (1, 2, 3, 4))
        hc = f"{e['hold_c']:+.1f} ({e['hold_events']})" if e["hold_c"] is not None else f"— ({e['hold_events']})"
        lines.append(f"| {e['kind']}:{e['name']} YES-price {e['bucket']} buy {e['side']} | {e['events']} | "
                     f"{e['net_c']:+.1f} | [{e['lo_c']:+.1f}, {e['hi_c']:+.1f}] | "
                     f"{e['old_c']} | {e['new_c']} | {hc} | {e['p']:.2g} | {g} | {'YES' if e['passed'] else ''} |")
    REPORT.write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:5]))
    for e in out[:12]:
        print(f"  {e['kind']}:{e['name'][:26]:26s} {e['bucket']:>8s} buy {e['side']:3s} events {e['events']:4d} "
              f"exec/approx {e['n_exec']}/{e['n_approx']} net {e['net_c']:+5.1f}c [{e['lo_c']:+.1f},{e['hi_c']:+.1f}] "
              f"halves {e['old_c']}/{e['new_c']} hold {e['hold_c']}({e['hold_events']}) p={e['p']:.2g} "
              f"gates {''.join('Y' if e.get(f'gate{i}') else '.' for i in (1, 2, 3, 4))} "
              f"{'PASS' if e['passed'] else ''}")
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
