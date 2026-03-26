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
from logger import log

FIELDNAMES = [
    "timestamp", "ticker", "title", "category",
    "direction", "edge_pct", "implied_prob", "true_prob", "confidence",
    "suggested_live_dollars", "suggested_paper_dollars",
    "is_paper_bet", "paper_entry_price_cents",
    "outcome",       # 1 = correct, 0 = wrong, "" = pending
    "resolved_at",
    "notes",
]


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


def auto_resolve_outcomes(api) -> int:
    """
    Check all pending outcomes against finalized Kalshi markets.
    Updates outcomes.csv in place. Returns count of newly resolved rows.
    """
    rows = read_all()
    pending = [r for r in rows if r.get("outcome") == "" and r.get("ticker")]
    if not pending:
        return 0

    # Fetch recently finalized markets from Kalshi
    finalized = api.get_settled_markets(limit=200)
    finalized_map = {}
    for m in finalized:
        ticker = m.get("ticker", "")
        result = m.get("result", "")   # "yes" or "no"
        if ticker and result:
            finalized_map[ticker] = result.lower()

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
            resolved_count += 1
            log(f"  Resolved {ticker}: result={result} direction={direction} "
                f"→ {'✅ correct' if correct else '❌ wrong'}")
        updated_rows.append(row)

    if resolved_count > 0:
        _rewrite(updated_rows)

    return resolved_count


def _rewrite(rows: list) -> None:
    with open(config.OUTCOMES_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        w.writerows(rows)


def hit_rate_summary() -> dict:
    """
    Calculate hit rate overall and by category/edge bucket.
    Returns a summary dict for the morning report.
    """
    rows = read_all()
    rated = [r for r in rows if r.get("outcome") in ("0", "1")]
    if not rated:
        return {"total_alerts": len(rows), "rated": 0, "hit_rate": None,
                "by_category": {}, "by_edge_bucket": {}}

    def _rate(subset):
        if not subset:
            return None
        hits = sum(1 for r in subset if r.get("outcome") == "1")
        return round(hits / len(subset) * 100, 1)

    # By category
    categories = set(r.get("category", "") for r in rated)
    by_cat = {}
    for cat in categories:
        sub = [r for r in rated if r.get("category") == cat]
        by_cat[cat] = {"count": len(sub), "hit_rate": _rate(sub)}

    # By edge bucket
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
        b = _bucket(r)
        buckets.setdefault(b, []).append(r)
    by_bucket = {b: {"count": len(sub), "hit_rate": _rate(sub)}
                 for b, sub in buckets.items()}

    return {
        "total_alerts": len(rows),
        "rated":        len(rated),
        "hit_rate":     _rate(rated),
        "by_category":  by_cat,
        "by_edge_bucket": by_bucket,
    }
