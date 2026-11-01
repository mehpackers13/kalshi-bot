"""
WEATHER TAIL — paper-only forward test (never places orders).

Idea, from a 2026-10-31 backtest of settled Kalshi markets (research/longshot_bias.py):
on daily-high temperature markets, the far-off "tail" strikes are priced at 2-30c for YES
but essentially never hit (0 of 320 in the sample), so buying NO at ~95c looked like
+4c/contract after fees. That was measured on past data with prices taken up to 36h before
close; this module checks it forward, with the price we could actually have filled.

Each scan:
  1. For open KXHIGH* markets 6-36h from close, YES priced 2-30c and with a YES bid to hit,
     record ONE paper entry per ticker: buy NO at (1 - yes_bid), i.e. as a taker, fee included.
  2. Resolve earlier entries once Kalshi has settled the market.
  3. Log a running summary (hit rate, net cents/contract, clustered by city-day).

Promotion to real money is a human decision: >= 30 settled city-days, positive net with the
95% interval above 0, and no YES hit that wipes out the gains. Nothing here trades.
"""
import csv, datetime, math, statistics, collections
import time

import config
import kalshi_api
from logger import log

LOG = config.DATA_DIR / "weather_tail_log.csv"
FIELDS = ["rule", "category", "ticker", "event", "entered_at", "hours_to_close", "yes_bid", "yes_ask", "no_cost",
          "status", "result", "fee", "pnl", "resolved_at"]
PREFIX = "KXHIGH"
MIN_H, MAX_H = 6.0, 36.0
MIN_YES, MAX_YES = 0.02, 0.30
# Second rule, from the strategy lab (data/LAB_REPORT.md): YES contracts priced 10-30c are
# overpriced across categories, so buy NO. Paper only; capped per scan to keep the log small.
LS_MIN, LS_MAX, LS_CAP = 0.10, 0.30, 40
LS_MIN_CONTRACTS = 200        # same liquidity bar as strategy_lab.MIN_VOL


def _fee(p: float) -> float:
    return math.ceil(0.07 * p * (1 - p) * 100) / 100


def _event(ticker: str) -> str:
    return "-".join(ticker.split("-")[:2])


def _load() -> list:
    if not LOG.exists():
        return []
    with open(LOG, newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:                                    # rows written before rules existed
        r.setdefault("rule", "") ; r["rule"] = r["rule"] or "weather_tail"
    return rows


def _save(rows: list) -> None:
    config.DATA_DIR.mkdir(exist_ok=True)
    with open(LOG, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def record_entries(rows: list, markets: list) -> int:
    seen = {r["ticker"] for r in rows}
    now = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    added = 0
    for m in markets:
        t = m["ticker"]
        if not t.startswith(PREFIX) or t in seen:
            continue
        if not (MIN_H <= m["hours_to_close"] <= MAX_H):
            continue
        yes_bid, yes_ask = m["yes_bid"] / 100.0, m["yes_ask"] / 100.0
        mid = (yes_bid + yes_ask) / 2
        if yes_bid < 0.01 or not (MIN_YES <= mid <= MAX_YES):
            continue
        rows.append({"rule": "weather_tail", "category": "Climate and Weather", "ticker": t,
                     "event": _event(t), "entered_at": now,
                     "hours_to_close": round(m["hours_to_close"], 1), "yes_bid": yes_bid,
                     "yes_ask": yes_ask, "no_cost": round(1 - yes_bid, 2), "status": "open"})
        added += 1
    return added


def record_longshot(rows: list, markets: list) -> int:
    """Rule 2: buy NO when a liquid, non-weather, non-combo market has YES at 10-30c."""
    seen = {r["ticker"] for r in rows}
    now = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    added = 0
    for m in sorted(markets, key=lambda x: -x.get("volume", 0)):
        t = m["ticker"]
        if added >= LS_CAP:
            break
        if t in seen or t.startswith(("KXMVE", PREFIX)) or m.get("volume", 0) < LS_MIN_CONTRACTS:
            continue
        if not (MIN_H <= m["hours_to_close"] <= MAX_H):
            continue
        yes_bid, yes_ask = m["yes_bid"] / 100.0, m["yes_ask"] / 100.0
        if yes_bid < 0.01 or not (LS_MIN <= (yes_bid + yes_ask) / 2 < LS_MAX):
            continue
        rows.append({"rule": "longshot_no_10_30", "category": m.get("category") or "unknown", "ticker": t,
                     "event": _event(t), "entered_at": now, "hours_to_close": round(m["hours_to_close"], 1),
                     "yes_bid": yes_bid, "yes_ask": yes_ask, "no_cost": round(1 - yes_bid, 2), "status": "open"})
        added += 1
    return added


def resolve(rows: list, api) -> int:
    done = 0
    for r in rows:
        if r.get("status") != "open":
            continue
        entered = datetime.datetime.fromisoformat(r["entered_at"].rstrip("Z"))
        if (datetime.datetime.utcnow() - entered).total_seconds() < float(r["hours_to_close"]) * 3600:
            continue                                  # market can't have closed yet
        mk = api.get_market(r["ticker"]) or {}
        result = mk.get("result")
        if result not in ("yes", "no"):
            continue
        cost = float(r["no_cost"])
        fee = _fee(cost)
        pnl = ((1 - cost) if result == "no" else -cost) - fee
        r.update(status="settled", result=result, fee=fee, pnl=round(pnl, 4),
                 resolved_at=datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z")
        done += 1
    return done


def summarize(rows: list) -> str:
    rules = sorted({r["rule"] for r in rows}) or ["weather_tail"]
    return " | ".join(_summarize_rule([r for r in rows if r["rule"] == rule], rule) for rule in rules)


def _summarize_rule(rows: list, rule: str) -> str:
    settled = [r for r in rows if r.get("status") == "settled"]
    if not settled:
        return f"{rule}: {sum(1 for r in rows if r.get('status') == 'open')} open, none settled yet"
    ev = collections.defaultdict(list)
    for r in settled:
        ev[r["event"]].append(float(r["pnl"]))
    em = [statistics.mean(v) for v in ev.values()]
    mean = statistics.mean(em)
    hits = sum(1 for r in settled if r["result"] == "yes")
    ci = ""
    if len(em) >= 3:
        se = statistics.stdev(em) / math.sqrt(len(em))
        ci = f", 95% CI [{(mean - 2 * se) * 100:+.1f}, {(mean + 2 * se) * 100:+.1f}]c"
    return (f"{rule}: {len(settled)} settled across {len(ev)} events, YES hit {hits}x, "
            f"net {mean * 100:+.1f}c/contract{ci}; {sum(1 for r in rows if r.get('status') == 'open')} open")


def fetch_weather_markets(api) -> list:
    """Open daily-high markets, fetched by series. The scanner's general fetch is
    capped at 50 event pages and never returns these, so ask for them directly."""
    data = api._get("/series", params={"category": "Climate and Weather"}) or {}
    series = sorted({x["ticker"] for x in data.get("series", []) if x.get("ticker", "").startswith(PREFIX)})
    out = []
    for s in series:
        d = api._get("/markets", params={"series_ticker": s, "status": "open", "limit": 1000}) or {}
        out += [m for m in (kalshi_api.parse_market(r) for r in d.get("markets", [])) if m]
        time.sleep(0.1)
    return out


def run(api, markets: list = None) -> None:
    rows = _load()
    added = record_entries(rows, fetch_weather_markets(api))
    # The scanner's own list is almost all long-dated, so ask for the fast markets directly.
    added += record_longshot(rows, api.get_closing_soon(MIN_H, MAX_H))
    done = resolve(rows, api)
    _save(rows)
    log(f"{summarize(rows)} (+{added} new, {done} resolved)")
