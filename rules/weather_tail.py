"""weather_tail: KXHIGH* daily-high markets 6-36h from close, YES mid 2-30c, a YES bid to hit -> buy NO."""
import time

import kalshi_api
from logger import log

NAME = "weather_tail"
CAP = 150
PREFIX = "KXHIGH"
MIN_H, MAX_H = 6.0, 36.0
MIN_YES, MAX_YES = 0.02, 0.30


def series_of(m: dict) -> str:
    return m.get("series") or m["ticker"].split("-")[0]


def fetch_by_series(api, prefixes=(PREFIX,)) -> list:
    """Fallback when the scanner feed has no weather rows: fetch open markets series by series."""
    data = api._get("/series", params={"category": "Climate and Weather"}) or {}
    series = sorted({x["ticker"] for x in data.get("series", []) if x.get("ticker", "").startswith(tuple(prefixes))})
    out = []
    for s in series:
        d = api._get("/markets", params={"series_ticker": s, "status": "open", "limit": 1000}) or {}
        for raw in d.get("markets", []):
            m = kalshi_api.parse_market(raw)
            if m:
                m["series"] = s
                out.append(m)
        time.sleep(0.1)
    return out


MIN_FEED_ROWS = 40     # a healthy feed has hundreds of weather rows; fewer means it is not carrying them


_FETCHED = {}          # prefixes -> (ts, markets) so two weather rules share one by-series fetch per scan


def universe(ctx, prefixes=(PREFIX,)) -> list:
    ms = [m for m in ctx["markets"] if series_of(m).startswith(tuple(prefixes))]
    if len(ms) < MIN_FEED_ROWS:
        log(f"{NAME}: only {len(ms)} {prefixes} rows in feed, fetching by series")
        hit = _FETCHED.get(tuple(prefixes))
        if not hit or time.time() - hit[0] > 300:
            hit = (time.time(), fetch_by_series(ctx["api"], prefixes))
            _FETCHED[tuple(prefixes)] = hit
        have = {m["ticker"] for m in ctx["markets"]}
        for m in hit[1]:
            if m["ticker"] not in have:               # also make them priceable by paper_lab
                ctx["markets"].append(m)
        ms = [m for m in ctx["markets"] if series_of(m).startswith(tuple(prefixes))]
    return ms


def tail_ok(m: dict) -> bool:
    if not (MIN_H <= m["hours_to_close"] <= MAX_H):
        return False
    yb, ya = m["yes_bid"] / 100.0, m["yes_ask"] / 100.0
    return yb >= 0.01 and MIN_YES <= (yb + ya) / 2 <= MAX_YES


def select(ctx) -> list:
    out = []
    for m in universe(ctx):
        if tail_ok(m):
            out.append({"ticker": m["ticker"], "side": "NO", "category": "Climate and Weather",
                        "series": series_of(m), "model_prob": None, "notes": "tail 2-30c, buy NO"})
    return out
