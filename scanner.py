"""
MARKET SCANNER
==============
Fetches all open Kalshi markets, filters them, runs edge detection,
and fires Discord alerts only when a genuine edge is found.
Silent by design — no alerts = good discipline.
"""

import datetime
from typing import Optional

import config
from kalshi_api import KalshiAPI, parse_market
from edge_calculator import calculate_edge, EdgeResult
from kelly import size_bet
from bankroll import check_drawdown_stop, sync_live_balance
from outcomes import log_alert, auto_resolve_outcomes, read_all
from discord_alerts import send_trade_alert, send_drawdown_stop, send_health_ping
from logger import log


def _already_alerted_today(ticker: str) -> bool:
    """Don't fire duplicate alerts for the same market in the same day."""
    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    rows  = read_all()
    for row in rows:
        if row.get("ticker") == ticker and row.get("timestamp", "").startswith(today):
            return True
    return False


def run_scan(api: KalshiAPI) -> list:
    """
    Full scan cycle. Returns list of EdgeResult objects that were alerted.
    """
    log("=" * 60)
    log("Starting market scan")

    # Safety: check drawdown stop before doing anything
    if check_drawdown_stop():
        from bankroll import load_bankroll
        br = load_bankroll()
        send_drawdown_stop(br["live"]["balance"], br["live"]["start"])
        log("Drawdown stop active — scan aborted", "WARN")
        return []

    # Sync live balance from Kalshi
    sync_live_balance(api)

    # Auto-resolve any pending outcomes
    resolved = auto_resolve_outcomes(api)
    if resolved:
        log(f"Auto-resolved {resolved} market outcomes")

    # Fetch all open markets
    raw_markets = api.get_all_open_markets()
    log(f"Fetched {len(raw_markets)} open markets")

    # Parse and filter
    markets = []
    for raw in raw_markets:
        parsed = parse_market(raw)
        if parsed:
            markets.append(parsed)

    log(f"Parsed {len(markets)} valid markets")

    # Category breakdown
    cat_counts = {}
    for m in markets:
        cat = m.get("category", "Unknown")
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
    log(f"Categories: {dict(sorted(cat_counts.items(), key=lambda x: -x[1])[:8])}")

    # Edge detection
    edges_found = []
    skipped_cats = set()
    checked = 0

    for market in markets:
        category = market.get("category", "")

        # Only run expensive models on modelable categories
        if category not in config.MODELABLE_CATEGORIES:
            skipped_cats.add(category)
            continue

        # Skip if already alerted for this market today
        if _already_alerted_today(market["ticker"]):
            continue

        checked += 1
        edge = calculate_edge(market)
        if edge is not None:
            edges_found.append(edge)

    log(f"Checked {checked} modelable markets | Found {len(edges_found)} edges")
    if skipped_cats:
        log(f"Skipped (no model): {', '.join(sorted(skipped_cats))}")

    # Alert and log
    alerted = []
    for edge in edges_found:
        sizing = size_bet(edge)

        if sizing["live_dollars"] < 0.50 and sizing["paper_dollars"] < 1.00:
            log(f"  Skipping {edge.ticker} — suggested bet too small to be meaningful")
            continue

        send_trade_alert(edge, sizing)
        log_alert(edge, sizing)
        alerted.append(edge)

    if not alerted:
        log("Scan complete — no qualifying edges found (this is fine)")
    else:
        log(f"Scan complete — {len(alerted)} alerts sent")

    log("=" * 60)
    return alerted


def premarket_watch(api: KalshiAPI, max_markets: int = 10) -> list:
    """
    Lightweight scan to find markets worth watching for the morning report.
    Returns top candidates sorted by edge size.
    """
    raw_markets = api.get_all_open_markets()
    candidates  = []

    for raw in raw_markets:
        m = parse_market(raw)
        if not m:
            continue
        if m.get("category") not in config.MODELABLE_CATEGORIES:
            continue
        edge = calculate_edge(m)
        if edge and abs(edge.edge_pct) >= config.MIN_EDGE_PCT:
            candidates.append({
                "ticker":   edge.ticker,
                "title":    edge.title,
                "edge_pct": edge.edge_pct,
                "category": edge.category,
                "confidence": edge.confidence,
            })

    candidates.sort(key=lambda x: -abs(x["edge_pct"]))
    return candidates[:max_markets]
