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
import config
from logger import log

LOG = config.DATA_DIR / "weather_tail_log.csv"
FIELDS = ["ticker", "event", "entered_at", "hours_to_close", "yes_bid", "yes_ask", "no_cost",
          "status", "result", "fee", "pnl", "resolved_at"]
PREFIX = "KXHIGH"
MIN_H, MAX_H = 6.0, 36.0
MIN_YES, MAX_YES = 0.02, 0.30


def _fee(p: float) -> float:
    return math.ceil(0.07 * p * (1 - p) * 100) / 100


def _event(ticker: str) -> str:
    return "-".join(ticker.split("-")[:2])


def _load() -> list:
    if not LOG.exists():
        return []
    with open(LOG, newline="") as f:
        return list(csv.DictReader(f))


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
        rows.append({"ticker": t, "event": _event(t), "entered_at": now,
                     "hours_to_close": round(m["hours_to_close"], 1), "yes_bid": yes_bid,
                     "yes_ask": yes_ask, "no_cost": round(1 - yes_bid, 2), "status": "open"})
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
    settled = [r for r in rows if r.get("status") == "settled"]
    if not settled:
        return f"weather-tail: {sum(1 for r in rows if r.get('status') == 'open')} open, none settled yet"
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
    return (f"weather-tail: {len(settled)} settled across {len(ev)} city-days, YES hit {hits}x, "
            f"net {mean * 100:+.1f}c/contract{ci}; {sum(1 for r in rows if r.get('status') == 'open')} open")


def run(api, markets: list) -> None:
    rows = _load()
    added = record_entries(rows, markets)
    done = resolve(rows, api)
    _save(rows)
    log(f"{summarize(rows)} (+{added} new, {done} resolved)")
