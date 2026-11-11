"""
HISTORY HARVEST — builds a large executable-price history of settled Kalshi markets.

Why this exists
---------------
strategy_lab.py caps its own fetch (last 90 days, 40 markets/series, 60 series/category), so
data/lab_cache.json plateaued near 4,500 markets. At that size almost no series reaches the
lab's 30-independent-event PASS gate, so promising rules (e.g. KXLOLGAME NO 10-30% at +16c over
10 events) can be neither confirmed nor rejected. The bottleneck is sample size, not edge.

This harvester removes the caps and runs as a long background job:

  1. DISCOVER settled markets by paging /markets?status=settled with a cursor, sliced into
     close-time windows so no single cursor walk is truncated (same fix as the scanner feed).
     Discovery is cheap: ~200 markets per request.
  2. QUOTE each market with ONE candlesticks call, which yields the executable yes_ask / yes_bid
     in the 36h->3h pre-close window. strategy_lab's entry_cost()/yes_price() use only those two
     fields for rows where px_src == 'candle', so the old second call to /markets/trades (for a
     VWAP that can never make a rule PASS) is skipped. That halves the per-market cost.

Kalshi's rate limit is global and server-side: measured ~5-7 requests/second regardless of client
concurrency (32 threads returned mostly 429s). So this uses a single adaptive token bucket rather
than a big thread pool, and is built to run for hours and be resumed.

Rows are written into data/lab_cache.json in exactly the schema strategy_lab.py expects, so
`python strategy_lab.py --analyse-only` picks them up with no further changes.

'px' is recorded as the candle mid. It feeds only the legacy VWAP comparison columns, which exist
to show how much the pre-fee/pre-spread method overstated returns and can never make a rule PASS.

Usage
-----
    python history_harvest.py --discover            # build/refresh the work list only
    python history_harvest.py --years 3 --minutes 0 # discover + quote until the work list is done
    python history_harvest.py --minutes 90          # quote for 90 minutes, then stop (resumable)
    python history_harvest.py --status              # show progress, make no API calls
"""
import argparse, collections, datetime, gzip, json, os, threading, time, zlib
import requests
import config

BASE = config.KALSHI_BASE_URL
CACHE = config.DATA_DIR / "lab_cache.json"          # the lab's existing 4.5k cache (read-only here)
HISTORY = config.DATA_DIR / "history.jsonl.gz"      # append-only harvest output
WORKLIST = config.DATA_DIR / "harvest_worklist.json"
STATE = config.DATA_DIR / "harvest_state.json"

MIN_VOL = 200          # same liquidity floor as strategy_lab
MIN_LIFETIME = 5 * 3600  # a market must outlive the lab's 3h-before-close entry edge to have a candle
WINDOW_DAYS = 7        # close-time slice width for discovery
PAGE_LIMIT = 200
RATE_START = 4.0       # requests/sec, adapts down on 429 and back up on success
RATE_MIN, RATE_MAX = 0.7, 7.0
SAVE_EVERY = 200       # flush cache this often


# ----------------------------------------------------------------------------- http

class Limiter:
    """Adaptive token bucket. Kalshi's limit is global, so one shared pacer beats many threads."""

    def __init__(self, rate=RATE_START):
        self.rate = rate
        self.next_at = 0.0
        self.lock = threading.Lock()
        self.n429 = 0
        self.nok = 0

    def wait(self):
        with self.lock:
            now = time.time()
            due = max(now, self.next_at)
            self.next_at = due + 1.0 / self.rate
        if due > now:
            time.sleep(due - now)

    def hit_429(self):
        with self.lock:
            self.n429 += 1
            self.rate = max(RATE_MIN, self.rate * 0.6)

    def ok(self):
        with self.lock:
            self.nok += 1
            if self.nok % 40 == 0:
                self.rate = min(RATE_MAX, self.rate * 1.08)


LIM = Limiter()
S = requests.Session()


def get(path, params=None, tries=5):
    """Rate-paced GET. Returns parsed JSON, or None after exhausting retries."""
    for attempt in range(tries):
        LIM.wait()
        try:
            r = S.get(BASE + path, params=params, timeout=30)
        except Exception:
            time.sleep(1.5 * (attempt + 1))
            continue
        if r.status_code == 200:
            LIM.ok()
            try:
                return r.json()
            except ValueError:
                return None
        if r.status_code == 429:
            LIM.hit_429()
            time.sleep(0.8 * (attempt + 1))
            continue
        if 500 <= r.status_code < 600:
            time.sleep(1.0 * (attempt + 1))
            continue
        return None     # 404 / 400: market has no archived candles, do not retry
    return None


def ts(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def series_of(ticker):
    return ticker.split("-")[0]


def load_json(p, default):
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


def atomic_write(p, obj):
    tmp = str(p) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f)
    os.replace(tmp, p)


def series_categories():
    """series_ticker -> category, from the cache kalshi_api writes (data/series_categories.json).
    Read straight off disk so a harvest run costs no API calls for this."""
    d = load_json(config.DATA_DIR / "series_categories.json", {})
    m = d.get("map", d) if isinstance(d, dict) else {}
    if not m:
        print("warn: series_categories.json empty; categories will be 'Unknown'")
    else:
        print(f"series categories: {len(m)} series")
    return m


# ----------------------------------------------------------------------------- discovery

def discover(years, cats_by_series):
    """Page settled markets in close-time slices; return {ticker: row-stub} for liquid, resolved ones."""
    cache = set(load_json(CACHE, {})) | set(load_history())   # discovery only reads
    work = load_json(WORKLIST, {})
    now = int(time.time())
    start = now - int(years * 365.25 * 86400)
    slices = []
    t = start
    while t < now:
        slices.append((t, min(now, t + WINDOW_DAYS * 86400)))
        t += WINDOW_DAYS * 86400
    slices.reverse()        # newest first: most likely to have candles and matter most

    added = skipped = 0
    for i, (lo, hi) in enumerate(slices):
        cursor, pages = None, 0
        while pages < 60:
            params = {"status": "settled", "limit": PAGE_LIMIT, "mve_filter": "exclude",
                      "min_close_ts": lo, "max_close_ts": hi}
            if cursor:
                params["cursor"] = cursor
            d = get("/markets", params)
            if not d:
                break
            mk = d.get("markets", [])
            for m in mk:
                tk = m.get("ticker")
                if not tk or tk in cache:
                    skipped += 1
                    continue
                if m.get("result") not in ("yes", "no") or not m.get("close_time"):
                    continue
                vol = float(m.get("volume_fp") or m.get("volume") or 0)
                if vol < MIN_VOL:
                    continue
                close = int(ts(m["close_time"]))
                # Market lifetime. The lab's entry is 3-36h before close, so a market that
                # existed for only minutes or a couple of hours (KXDOGE15M and friends) has
                # no candle in that window at all. Measured: quoting them blind gave only a
                # ~25% candle hit rate, i.e. 4 API calls per usable row against a global
                # ~5 req/s limit. Recording the lifetime lets quoting skip them for free.
                dur = None
                if m.get("open_time") or m.get("created_time"):
                    try:
                        dur = int(close - ts(m.get("open_time") or m["created_time"]))
                    except Exception:
                        dur = None
                if tk in work:
                    if dur is not None and work[tk].get("dur") is None:
                        work[tk]["dur"] = dur       # backfill for an earlier discovery pass
                    skipped += 1
                    continue
                s = series_of(tk)
                work[tk] = {"series": s, "cat": cats_by_series.get(s, "Unknown"),
                            "yes": 1 if m["result"] == "yes" else 0,
                            "close": close, "vol": int(vol), "dur": dur}
                added += 1
            cursor, pages = d.get("cursor"), pages + 1
            if not cursor or not mk:
                break
        if i % 5 == 0 or i == len(slices) - 1:
            day = datetime.datetime.utcfromtimestamp(lo).strftime("%Y-%m-%d")
            print(f"  discover {i+1:3d}/{len(slices)} week of {day}  worklist={len(work)}  "
                  f"(+{added} new, {skipped} already have)  rate={LIM.rate:.1f}/s", flush=True)
            atomic_write(WORKLIST, work)
    atomic_write(WORKLIST, work)
    print(f"discover: worklist {len(work)} markets to quote (+{added} new this pass)")
    return work


# ----------------------------------------------------------------------------- quoting

def candle_quote(series, ticker, close):
    """One call -> executable quote. Mirrors strategy_lab.candle_quote's window and validation.
    Returns dict with px_src 'candle'/'nocandle', or None on an error worth retrying later."""
    params = {"start_ts": int(close - 36 * 3600), "end_ts": int(close - 3 * 3600),
              "period_interval": 60}
    d = get(f"/series/{series}/markets/{ticker}/candlesticks", params)
    if not isinstance(d, dict):
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
            return {"px_yes_ask": round(ask, 4), "px_yes_bid": round(bid, 4),
                    "px": round((ask + bid) / 2, 4), "px_src": "candle"}
    return {"px_src": "nocandle"}


def load_history():
    """{ticker: row} from the append-only harvest file."""
    return read_history(HISTORY)[0]


def repair_history():
    """Rewrite the harvest file from its readable prefix if it is torn.

    This matters more than it looks. A gzip stream cannot resync after a damaged member,
    so a tear in the MIDDLE of the file makes every row appended after it unreachable --
    the reader stops at the tear. Since the harvester appends, an interrupted run would
    otherwise leave it writing hours of rate-limited work into dead space behind the tear.
    Repairing on startup keeps the file append-only in the normal case and self-healing
    after a kill, crash, OOM or cancelled CI job."""
    rows, torn = read_history(HISTORY)
    if not torn:
        return rows
    tmp = str(HISTORY) + ".repair"
    with gzip.open(tmp, "wt") as f:
        for tk, r in rows.items():
            out = {"t": tk}
            out.update(r)
            f.write(json.dumps(out) + "\n")
    os.replace(tmp, HISTORY)
    print(f"repair: rewrote {HISTORY.name} with its {len(rows)} readable rows; "
          f"anything lost after the tear will simply be re-quoted", flush=True)
    return rows


def read_history(path):
    """Read gzipped JSONL, tolerating a truncated tail.

    The file is opened in append mode, so an interrupted run (kill, crash, cancelled CI
    job) leaves a torn final gzip member, and reading it WHILE a harvest is appending hits
    a half-written member. Both raise from the line ITERATOR, not from json.loads, so the
    exception has to be caught around the loop -- catching it per line leaves the file
    unreadable and silently discards every row already harvested.

    zlib.error ('invalid block type') is a plain Exception, not an OSError, so it has to
    be named explicitly; it is what a concurrent read actually raises.

    Returns (rows, torn)."""
    rows, torn = {}, False
    if not path.exists():
        return rows, torn
    try:
        with gzip.open(path, "rt") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                    rows[r.pop("t")] = r
                except Exception:
                    continue            # a single malformed row
    except (EOFError, OSError, zlib.error, gzip.BadGzipFile) as exc:
        torn = True
        print(f"warn: {path.name} torn ({type(exc).__name__}); readable rows: {len(rows)}. "
              f"Rows written after the tear are unreachable until repaired.", flush=True)
    return rows, torn


def quote_all(minutes):
    """Quote worklist markets until it is empty or the time budget runs out. Resumable.

    Rows are APPENDED to data/history.jsonl.gz. Appending matters: rewriting a whole
    200k-row JSON every few hundred markets would be quadratic and would also make the
    file unusable in git. Already-quoted tickers are skipped on the next run."""
    have = set(load_json(CACHE, {})) | set(repair_history())
    work = load_json(WORKLIST, {})
    state = load_json(STATE, {})
    # A market must have lived long enough to have a candle in the 36h->3h pre-close window.
    # dur is None for rows discovered before lifetimes were recorded: quote those anyway.
    todo = [tk for tk in work if tk not in have
            and (work[tk].get("dur") is None or work[tk]["dur"] >= MIN_LIFETIME)]
    n_short = sum(1 for tk in work if tk not in have
                  and work[tk].get("dur") is not None and work[tk]["dur"] < MIN_LIFETIME)
    if n_short:
        print(f"quote: skipping {n_short} markets that lived < {MIN_LIFETIME // 3600}h "
              f"(no candle possible in the 3-36h pre-close entry window)")
    # newest close first: best candle coverage, and most relevant to today's markets
    todo.sort(key=lambda tk: -work[tk]["close"])
    deadline = time.time() + minutes * 60 if minutes else float("inf")
    t0 = time.time()
    done = ok = nocandle = err = 0
    print(f"quote: {len(todo)} markets to quote, already have {len(have)}"
          f"{f', stopping after {minutes}m' if minutes else ''}", flush=True)
    f = gzip.open(HISTORY, "at")
    try:
        for tk in todo:
            if time.time() > deadline:
                print("quote: time budget reached, stopping cleanly", flush=True)
                break
            w = work[tk]
            q = candle_quote(w["series"], tk, w["close"])
            done += 1
            if q is None:
                err += 1
                continue        # transient: leave in the worklist for the next run
            row = {"t": tk, "series": w["series"], "cat": w["cat"],
                   "yes": w["yes"], "close": w["close"]}
            row.update(q)
            if q.get("px_src") == "candle":
                ok += 1
            else:
                nocandle += 1
                row["px"] = None
            f.write(json.dumps(row) + "\n")
            if done % SAVE_EVERY == 0:
                f.flush()
                el = time.time() - t0
                print(f"  quoted {done}/{len(todo)}  candle={ok} nocandle={nocandle} err={err}  "
                      f"{done/el:.1f}/s  rate={LIM.rate:.1f}/s  429s={LIM.n429}", flush=True)
    finally:
        f.close()
    state["last_quote_run"] = {"done": done, "candle": ok, "nocandle": nocandle, "err": err,
                               "secs": int(time.time() - t0)}
    atomic_write(STATE, state)
    print(f"quote: +{done} processed ({ok} candle, {nocandle} no traded candle, {err} errors)")


# ----------------------------------------------------------------------------- status

def status():
    merged = dict(load_json(CACHE, {}))
    hist = load_history()
    merged.update(hist)
    work = load_json(WORKLIST, {})
    exe = sum(1 for v in merged.values() if v.get("px_src") == "candle")
    left = sum(1 for tk in work if tk not in merged)
    by = collections.Counter(v["cat"] for v in merged.values() if v.get("px_src") == "candle")
    ev = collections.defaultdict(set)
    for tk, v in merged.items():
        if v.get("px_src") == "candle":
            ev[v["series"]].add("-".join(tk.split("-")[:2]))
    ready = sorted(((len(e), s) for s, e in ev.items() if len(e) >= 30), reverse=True)
    print(f"lab cache      : {len(load_json(CACHE, {}))} markets")
    print(f"harvest file   : {len(hist)} markets  ({HISTORY.name})")
    print(f"merged         : {len(merged)} markets, {exe} with executable candle quotes")
    print(f"worklist left  : {left}")
    print(f"series >=30 ev : {len(ready)} of {len(ev)}  <- these can reach the lab PASS gate")
    for n, s in ready[:15]:
        print(f"    {s:24s} {n} events")
    for c, n in by.most_common():
        print(f"  {c:22s} {n}")
    st = load_json(STATE, {}).get("last_quote_run")
    if st:
        print("last run       :", json.dumps(st))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=float, default=3.0, help="how far back to discover")
    ap.add_argument("--minutes", type=int, default=0, help="quote time budget (0 = until done)")
    ap.add_argument("--discover", action="store_true", help="discovery only")
    ap.add_argument("--quote", action="store_true", help="quoting only (use existing worklist)")
    ap.add_argument("--status", action="store_true", help="print progress, no API calls")
    a = ap.parse_args()

    if a.status:
        return status()
    if not a.quote:
        cats = series_categories()
        discover(a.years, cats)
    if not a.discover:
        quote_all(a.minutes)
    status()


if __name__ == "__main__":
    main()
