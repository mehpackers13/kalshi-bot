"""Probe the new close-window feed vs the old events feed. Read-only, public data."""
import os
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kalshi_api import KalshiAPI, parse_market  # noqa: E402

WANT = ["Crypto", "Climate and Weather", "Sports"]


def summarize(name, raw):
    parsed = [m for m in (parse_market(r) for r in raw) if m]
    cats = Counter((m["category"] or "Unknown") for m in parsed)
    bins = Counter()
    for m in parsed:
        h = m["hours_to_close"]
        k = "<=6h" if h <= 6 else "6-36h" if h <= 36 else "36h-7d" if h <= 168 else "7-60d" if h <= 1440 else ">60d"
        bins[k] += 1
    print("== %s: raw %d, parsed %d" % (name, len(raw), len(parsed)))
    print("  categories:", dict(cats.most_common(15)))
    print("  hours-to-close:", {k: bins.get(k, 0) for k in ["<=6h", "6-36h", "36h-7d", "7-60d", ">60d"]})
    print("  wanted:", {c: cats.get(c, 0) for c in WANT})
    return cats


if __name__ == "__main__":
    api = KalshiAPI()
    t = time.time()
    api.get_series_categories()
    print("series map: %d series in %.1fs" % (len(KalshiAPI._series_cat_cache), time.time() - t))
    t = time.time()
    new = api.get_all_open_markets()
    dt = time.time() - t
    print("new feed: %d markets in %.1fs" % (len(new), dt))
    summarize("NEW window feed", new)
    t = time.time()
    old = api.get_all_open_markets_events()
    print("old events feed: %d markets in %.1fs" % (len(old), time.time() - t))
    summarize("OLD events feed", old)
