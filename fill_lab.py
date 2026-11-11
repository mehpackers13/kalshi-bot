"""
FILL LAB — measure adverse selection on resting orders, the one number maker_lab assumes.

The question
------------
maker_lab.py shows that posting instead of taking is worth roughly +3c/contract on
Kalshi's fee-free series, turning five of six price buckets positive. But every one of
those figures assumes a resting order always fills at the touch, and that assumption is
exactly where maker strategies die: a posted bid fills when someone decides to sell into
it, which is disproportionately when the market is about to go against you.

That is why the published study (Burgi, Deng & Whelan, UCD 2026, 313,972 contracts) finds
real makers averaging -9.64% rather than the small profit "cross the spread for free"
implies. Their -9.64% and maker_lab's +1c are the SAME strategy measured with and without
adverse selection. The gap between them is the number this script estimates.

Why this is measurable from history
-----------------------------------
It looked like it needed live observation, but it does not. Kalshi's /markets/trades
feed records every executed trade with its price and which side was the taker. So for a
settled market we can:

  1. Take the best bid B at the start of the lab's entry window (already harvested, from
     the hourly candle: px_yes_bid).
  2. Post a hypothetical resting YES bid at B.
  3. Ask whether any later trade in the window printed at a price BELOW B with the taker
     selling. A trade through our price means the book cleared our level, so a resting
     order at B would have been hit. Requiring strictly below B is deliberate: at exactly
     B we may be behind others in the queue, and we cannot see queue position.
  4. Score the outcome only for markets that would have filled.

Comparing filled-only returns against all-markets returns is the adverse selection
estimate. If posting is genuinely profitable, the two are close. If filling is a signal
that you were wrong, filled-only is much worse -- and that difference is the real cost.

This makes no assumption about fills; it reads what actually traded.

    python fill_lab.py --limit 600          # measure on 600 harvested markets
    python fill_lab.py --limit 3000 --side NO

Costs one /markets/trades call per market, so it shares Kalshi's global ~5 req/s limit
with history_harvest.py. Run it after a harvest finishes, not alongside one.
"""
import argparse, collections, datetime, json, math, statistics, time
import config
import history_harvest as hh
import strategy_lab as lab

RESULTS = config.DATA_DIR / "fill_results.json"
REPORT = config.DATA_DIR / "FILL_REPORT.md"

WINDOW_START_H = 36      # same entry window as the lab
WINDOW_END_H = 3
MAX_SPREAD = 0.02        # same tradeability filter as maker_lab


def fee(mult, p):
    return math.ceil(mult * p * (1 - p) * 100) / 100


def trades_in_window(ticker, close):
    """Executed trades in the entry window, oldest first."""
    out, cursor = [], None
    for _ in range(6):
        params = {"ticker": ticker, "min_ts": int(close - WINDOW_START_H * 3600),
                  "max_ts": int(close - WINDOW_END_H * 3600), "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        d = hh.get("/markets/trades", params)
        if not isinstance(d, dict):
            return None
        out += d.get("trades", [])
        cursor = d.get("cursor")
        if not cursor:
            break
    rows = []
    for t in out:
        try:
            px = float(t.get("yes_price_dollars") or t["yes_price"] / 100.0)
        except (KeyError, TypeError, ValueError):
            continue
        ts = t.get("created_time")
        rows.append({"px": px, "taker_side": (t.get("taker_side") or "").lower(), "ts": ts})
    return rows


def would_fill(trades, bid, side):
    """Did the book trade through our resting price?

    Buying YES at B fills if someone sells YES below B. A trade printing below B with the
    taker on the sell side means the resting bids at and above that price were consumed.
    Buying NO at 1-A is the mirror: a trade printing above A with the taker buying YES.
    Strictly through, never at, our price -- at our price we may sit behind the queue."""
    for t in trades:
        # Require an explicit taker side. Treating a missing side as a match would count
        # the same trade as a fill for both YES and NO and inflate the fill rate.
        if side == "YES":
            if t["px"] < bid and t["taker_side"] in ("no", "sell"):
                return True
        else:
            if t["px"] > bid and t["taker_side"] in ("yes", "buy"):
                return True
    return False


def summarise(vals, label):
    if len(vals) < 5:
        return None
    m = statistics.mean(vals)
    se = statistics.stdev(vals) / math.sqrt(len(vals))
    return {"label": label, "n": len(vals), "net_c": round(m * 100, 2),
            "lo_c": round((m - 2 * se) * 100, 2), "hi_c": round((m + 2 * se) * 100, 2)}


def run(limit, side, maker_mult):
    rows = {k: v for k, v in lab.load_cache().items()
            if v.get("px_src") == "candle"
            and (v["px_yes_ask"] - v["px_yes_bid"]) <= MAX_SPREAD}
    items = sorted(rows.items(), key=lambda kv: -kv[1]["close"])[:limit]
    if not items:
        print("no harvested markets with executable quotes; run history_harvest.py first")
        return
    print(f"fill_lab: {len(items)} markets, side {side}, maker fee mult {maker_mult}", flush=True)

    filled, unfilled, allm, err, nodata = [], [], [], 0, 0
    t0 = time.time()
    for i, (tk, r) in enumerate(items, start=1):
        bid, ask = r["px_yes_bid"], r["px_yes_ask"]
        cost = bid if side == "YES" else 1 - ask
        ref = bid if side == "YES" else ask
        if cost <= 0 or cost >= 1:
            continue
        win = r["yes"] if side == "YES" else 1 - r["yes"]
        net = win - cost - fee(maker_mult, cost)
        allm.append(net)
        tr = trades_in_window(tk, r["close"])
        if tr is None:
            err += 1
            continue
        if not tr:
            nodata += 1
            continue
        (filled if would_fill(tr, ref, side) else unfilled).append(net)
        if i % 100 == 0:
            el = time.time() - t0
            print(f"  {i}/{len(items)}  filled {len(filled)} unfilled {len(unfilled)} "
                  f"no-trades {nodata} err {err}  {i/el:.1f}/s", flush=True)

    s_all = summarise(allm, "all markets (maker_lab's assumption)")
    s_fill = summarise(filled, "would have filled")
    s_unfill = summarise(unfilled, "would NOT have filled")
    adverse = (round(s_all["net_c"] - s_fill["net_c"], 2)
               if s_all and s_fill else None)
    fill_rate = round(len(filled) / max(1, len(filled) + len(unfilled)), 3)

    res = {"generated": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
           "markets_attempted": len(items), "side": side, "maker_mult": maker_mult,
           "fill_rate": fill_rate, "no_trade_data": nodata, "errors": err,
           "all": s_all, "filled": s_fill, "unfilled": s_unfill,
           "adverse_selection_c": adverse}
    RESULTS.write_text(json.dumps(res, indent=1))

    lines = [f"# Fill Lab — {res['generated']}", "",
             "Measures the one number maker_lab.py assumes: whether a resting order fills, "
             "and whether filling means you were wrong.", "",
             f"{len(items)} harvested markets, buying {side} as a maker, "
             f"spread <= {MAX_SPREAD*100:.0f}c, entry window {WINDOW_START_H}h-{WINDOW_END_H}h "
             f"before close. A fill is counted only when a trade printed strictly THROUGH our "
             f"resting price with the taker on the opposite side, since at our own price we "
             f"cannot know our queue position.", "",
             f"- **Fill rate: {fill_rate:.1%}**", ""]
    for s in (s_all, s_fill, s_unfill):
        if s:
            lines.append(f"- {s['label']}: **{s['net_c']:+.2f}c** "
                         f"[{s['lo_c']:+.2f}, {s['hi_c']:+.2f}] on n={s['n']}")
    if adverse is not None:
        lines += ["", f"**Adverse selection: {adverse:+.2f}c/contract.** This is the amount "
                      f"maker_lab overstates the maker case by, because it scores every market "
                      f"rather than only the ones a resting order would actually have caught."]
    lines += ["", f"No trade data for {nodata} markets; {err} API errors.", "",
              "Research only. Nothing here places an order."]
    REPORT.write_text("\n".join(lines) + "\n")
    print()
    print("\n".join(lines[6:14]))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=600)
    ap.add_argument("--side", choices=["YES", "NO"], default="YES")
    ap.add_argument("--maker-mult", type=float, default=0.0)
    a = ap.parse_args()
    run(a.limit, a.side, a.maker_mult)


if __name__ == "__main__":
    main()
