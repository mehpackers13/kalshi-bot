"""
OUTCOME TRACKER
===============
Logs every alert to outcomes.csv and automatically resolves markets
by checking Kalshi's settled market data.
"""

import csv
import json
import datetime
from pathlib import Path
from typing import Optional

import config
import bankroll
from logger import log

FIELDNAMES = [
    "timestamp", "ticker", "title", "category",
    "direction", "edge_pct", "implied_prob", "true_prob", "confidence",
    "suggested_live_dollars", "suggested_paper_dollars",
    "is_paper_bet", "paper_entry_price_cents",
    "outcome",       # 1 = correct, 0 = wrong, "" = pending
    "units_pl",      # unit P&L at resolve time (1u = 1% of peak balance)
    "resolved_at",
    "notes",
]


def kalshi_fee(price: float) -> float:
    """Kalshi taker fee per $1 contract: 0.07 * P * (1-P), rounded up to the cent."""
    import math
    return math.ceil(0.07 * price * (1 - price) * 100) / 100


def realized_return(direction: str, implied_prob: float, won: bool) -> float:
    """
    Return per $1 staked on a binary contract, priced on the side ACTUALLY bet.

    implied_prob is the YES-side price (0-1). Buying YES costs p; buying NO
    costs 1-p. A win pays $1 per contract. Fees are charged per contract.

    The previous formula used 1/p - 1 for every win — it credited a NO bet
    on a 10% market (cost 90¢, wins 10¢) as a 9-to-1 payout, overstating
    NO-side wins by up to ~80x.
    """
    p = float(implied_prob or 0)
    cost = p if (direction or "YES").upper() == "YES" else 1 - p
    if cost <= 0 or cost >= 1:
        return 0.0
    fee = kalshi_fee(cost)
    if won:
        return (1 - cost - fee) / cost
    return (-cost - fee) / cost


def _ensure_csv():
    config.OUTCOMES_CSV.parent.mkdir(exist_ok=True)
    if not config.OUTCOMES_CSV.exists():
        with open(config.OUTCOMES_CSV, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()
        log(f"Created outcomes log at {config.OUTCOMES_CSV}")


def log_alert(edge, sizing: dict) -> None:
    """Append a new alert row to outcomes.csv."""
    _ensure_csv()
    row = {
        "timestamp":               datetime.datetime.utcnow().isoformat() + "Z",
        "ticker":                  edge.ticker,
        "title":                   edge.title,
        "category":                edge.category,
        "direction":               edge.direction,
        "edge_pct":                round(edge.edge_pct, 2),
        "implied_prob":            round(edge.implied_prob, 4),
        "true_prob":               round(edge.true_prob, 4),
        "confidence":              edge.confidence,
        "suggested_live_dollars":  sizing["live_dollars"],
        "suggested_paper_dollars": sizing["paper_dollars"],
        "is_paper_bet":            1,
        "paper_entry_price_cents": sizing["price_cents"],
        "outcome":                 "",
        "resolved_at":             "",
        "notes":                   "",
    }
    with open(config.OUTCOMES_CSV, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=FIELDNAMES).writerow(row)


def read_all() -> list:
    _ensure_csv()
    with open(config.OUTCOMES_CSV, newline="") as f:
        return [r for r in csv.DictReader(f) if r.get("timestamp")]


def auto_resolve_outcomes(api, pages: int = 1, limit: int = 200) -> int:
    """
    Check all pending outcomes against finalized Kalshi markets.
    Updates outcomes.csv in place. Returns count of newly resolved rows.

    pages/limit control how many finalized markets to pull from Kalshi.
    Default 1 page @ 200 catches recent settlements; pages=5 (1000 markets)
    is useful on scan runs after a backlog has built up.
    """
    rows = read_all()
    pending = [r for r in rows if r.get("outcome") == "" and r.get("ticker")]
    if not pending:
        return 0

    # Fetch recently finalized markets from Kalshi
    try:
        finalized = api.get_settled_markets(limit=limit, pages=pages)
    except TypeError:
        finalized = api.get_settled_markets(limit=limit)
    finalized_map = {}
    for m in finalized:
        ticker = m.get("ticker", "")
        result = m.get("result", "")   # "yes" or "no"
        if ticker and result:
            finalized_map[ticker] = result.lower()

    unit_size = bankroll.live_peak() * 0.01  # 1u = 1% of peak balance (auto-scales with deposits)
    resolved_count = 0
    updated_rows = []
    for row in rows:
        ticker = row.get("ticker", "")
        if row.get("outcome") == "" and ticker in finalized_map:
            result    = finalized_map[ticker]         # "yes" or "no"
            direction = row.get("direction", "YES")
            # Correct if our direction matches the result
            correct   = (direction == "YES" and result == "yes") or \
                        (direction == "NO"  and result == "no")
            row["outcome"]     = "1" if correct else "0"
            row["resolved_at"] = datetime.datetime.utcnow().isoformat() + "Z"
            # Calculate unit P&L — priced on the side actually bet, net of fees
            try:
                dollars  = float(row.get("suggested_live_dollars") or 0)
                imp_prob = float(row.get("implied_prob") or 0)
                ret = realized_return(direction, imp_prob, correct)
                row["units_pl"] = round(dollars * ret / unit_size, 3) if dollars > 0 else 0
            except Exception:
                row["units_pl"] = ""
            resolved_count += 1
            log(f"  Resolved {ticker}: result={result} direction={direction} "
                f"→ {'✅ correct' if correct else '❌ wrong'} ({row.get('units_pl', '?')}u)")
        updated_rows.append(row)

    if resolved_count > 0:
        _rewrite(updated_rows)

    return resolved_count


def _rewrite(rows: list) -> None:
    """
    Rewrite outcomes.csv. extrasaction="ignore" prevents DictWriter from
    raising when a row has unknown keys — historical rows sometimes end up
    with a None key when the source CSV had extra commas (e.g. unescaped
    quotes in title or notes), which crashed every subsequent resolution.
    """
    with open(config.OUTCOMES_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            # Strip any None key that may have been introduced by DictReader
            row.pop(None, None)
            w.writerow(row)


def distinct_resolved(rows: list) -> list:
    """One rated row per ticker (the first alert). The scanner re-logs an open
    market daily, so raw rows overcount."""
    first = {}
    for r in rows:
        if r.get("outcome") in ("0", "1"):
            first.setdefault(r.get("ticker"), r)
    return list(first.values())


def _row_return(r: dict) -> float:
    return realized_return(r.get("direction"), r.get("implied_prob"), r.get("outcome") == "1")


def unit_total_distinct(rows: list) -> float:
    """Net units: 1-unit stake per distinct resolved market, priced on the side
    bet, net of Kalshi taker fees. Recomputed (stored units_pl is not used)."""
    return round(sum(_row_return(r) for r in distinct_resolved(rows)), 3)


def audited_record(rows: list) -> dict:
    """Honest record: every market counted once."""
    resolved = distinct_resolved(rows)
    wins = sum(1 for r in resolved if r.get("outcome") == "1")
    by_cat = {}
    for r in resolved:
        c = r.get("category") or "Unknown"
        d = by_cat.setdefault(c, {"markets": 0, "wins": 0, "net_units": 0.0})
        d["markets"] += 1
        d["wins"] += 1 if r.get("outcome") == "1" else 0
        d["net_units"] += _row_return(r)
    for d in by_cat.values():
        d["net_units"] = round(d["net_units"], 3)
    return {
        "markets_alerted": len({r.get("ticker") for r in rows if r.get("ticker")}),
        "raw_rows": len(rows),
        "resolved_markets": len(resolved),
        "wins": wins,
        "hit_rate": round(wins / len(resolved) * 100, 1) if resolved else None,
        "net_units": unit_total_distinct(rows),
        "by_category": by_cat,
    }


def hit_rate_summary() -> dict:
    """Hit rate overall and by category/edge bucket, counting each market once."""
    rows = read_all()
    rated = distinct_resolved(rows)
    audited = audited_record(rows)
    total = audited["markets_alerted"]
    if not rated:
        return {"total_alerts": total, "rated": 0, "hit_rate": None,
                "by_category": {}, "by_edge_bucket": {}, "audited": audited}

    def _rate(subset):
        if not subset:
            return None
        hits = sum(1 for r in subset if r.get("outcome") == "1")
        return round(hits / len(subset) * 100, 1)

    by_cat = {}
    for cat in set(r.get("category", "") for r in rated):
        sub = [r for r in rated if r.get("category") == cat]
        by_cat[cat] = {"count": len(sub), "hit_rate": _rate(sub)}

    def _bucket(r):
        try:
            e = abs(float(r.get("edge_pct", 0)))
        except Exception:
            e = 0
        if e >= 25:  return "strong (25%+)"
        if e >= 15:  return "medium (15-25%)"
        return "small (8-15%)"

    buckets = {}
    for r in rated:
        buckets.setdefault(_bucket(r), []).append(r)
    by_bucket = {b: {"count": len(sub), "hit_rate": _rate(sub)} for b, sub in buckets.items()}

    return {
        "total_alerts": total,
        "rated":        len(rated),
        "hit_rate":     _rate(rated),
        "by_category":  by_cat,
        "by_edge_bucket": by_bucket,
        "audited":      audited,
    }
