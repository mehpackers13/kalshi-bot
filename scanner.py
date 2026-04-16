"""
MARKET SCANNER
==============
Fetches all open Kalshi markets, filters them, runs edge detection,
and fires Discord alerts only when a genuine edge is found.
Silent by design — no alerts = good discipline.
"""

import datetime
import json
from typing import Optional

import config
from kalshi_api import KalshiAPI, parse_market
from edge_calculator import calculate_edge, EdgeResult
from kelly import size_bet
from bankroll import check_drawdown_stop, sync_live_balance
from outcomes import log_alert, auto_resolve_outcomes, read_all
from discord_alerts import send_trade_alert, send_drawdown_stop, send_health_ping
import auto_bettor
from logger import log


def _write_positions_snapshot(api: KalshiAPI) -> None:
    """Write current open positions + entry info to data/positions.json for the dashboard."""
    try:
        import csv as _csv
        # Load entry info from bets_placed.csv
        entry_info = {}
        if config.BETS_PLACED_CSV.exists():
            with open(config.BETS_PLACED_CSV, newline="") as f:
                for row in _csv.DictReader(f):
                    t = row.get("ticker", "")
                    if t and t not in entry_info:
                        try:
                            entry_info[t] = {
                                "direction":     row.get("direction", ""),
                                "price_cents":   int(row.get("price_cents") or 0),
                                "dollars_risked":float(row.get("dollars_risked") or 0),
                                "title":         row.get("title", ""),
                                "timestamp":     row.get("timestamp", ""),
                            }
                        except Exception:
                            pass

        positions = api.get_portfolio_positions()
        snapshot = []
        for pos in positions:
            ticker   = pos.get("ticker", "")
            count_fp = float(pos.get("position_fp") or pos.get("position") or 0)
            if not ticker or count_fp == 0:
                continue

            entry = entry_info.get(ticker, {})
            direction    = entry.get("direction", "YES" if count_fp > 0 else "NO")
            entry_cents  = entry.get("price_cents", 0)
            dollars_risk = entry.get("dollars_risked", 0)

            # Get current market price
            current_cents = 0
            current_value = 0.0
            try:
                market = api.get_market(ticker)
                if market:
                    if direction == "YES":
                        bid_raw = float(market.get("yes_bid_dollars") or market.get("yes_bid", 0) or 0)
                        current_cents = int(round(bid_raw * 100 if bid_raw <= 1 else bid_raw))
                    else:
                        ask_raw = float(market.get("yes_ask_dollars") or market.get("yes_ask", 0) or 0)
                        yes_ask = int(round(ask_raw * 100 if ask_raw <= 1 else ask_raw))
                        current_cents = max(0, 100 - yes_ask)
                    current_value = round(abs(count_fp) * current_cents / 100, 2)
            except Exception:
                pass

            pl_dollars = 0.0
            if entry_cents > 0 and current_cents > 0:
                pl_dollars = round((current_cents - entry_cents) / 100 * abs(count_fp), 2)
            elif dollars_risk > 0 and current_value > 0:
                pl_dollars = round(current_value - dollars_risk, 2)

            snapshot.append({
                "ticker":        ticker,
                "title":         entry.get("title", ticker),
                "direction":     direction,
                "contracts":     int(abs(count_fp)),
                "entry_cents":   entry_cents,
                "current_cents": current_cents,
                "dollars_risked":dollars_risk,
                "current_value": current_value,
                "pl_dollars":    pl_dollars,
                "timestamp":     entry.get("timestamp", ""),
            })

        config.DATA_DIR.mkdir(exist_ok=True)
        (config.DATA_DIR / "positions.json").write_text(json.dumps(snapshot, indent=2))
        log(f"Positions snapshot: {len(snapshot)} open position(s)")
    except Exception as exc:
        log(f"Positions snapshot failed: {exc}", "WARN")


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

    # Sync live balance first so drawdown check uses current portfolio total,
    # not a potentially stale cached value.
    sync_live_balance(api)

    # Snapshot open positions for the dashboard
    _write_positions_snapshot(api)

    # Safety: check drawdown stop using fresh balance just fetched above
    if check_drawdown_stop():
        from bankroll import load_bankroll
        br = load_bankroll()
        send_drawdown_stop(br["live"]["balance"], br["live"]["peak"])
        log("Drawdown stop active — scan aborted", "WARN")
        return []

    # Cut any positions that have lost ≥60% AND have >48h until expiry
    cut = auto_bettor.cut_losing_positions(api)
    if cut:
        log(f"Cut {len(cut)} losing position(s): {cut}")

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
    # Note: we let estimate_true_probability() decide if it can model each market
    # based on title keywords. Skipping by category was causing all markets to be
    # dropped when Kalshi's API returns empty category strings.
    edges_found = []
    unmodelable = 0
    checked = 0

    for market in markets:
        # Skip if already alerted for this market today
        if _already_alerted_today(market["ticker"]):
            continue

        checked += 1
        edge = calculate_edge(market)
        if edge is not None:
            edges_found.append(edge)

    log(f"Checked {checked} markets | Modelable: {checked - unmodelable} | Edges found: {len(edges_found)}")

    # Alert and log
    alerted = []
    for edge in edges_found:
        sizing = size_bet(edge)

        if sizing["live_dollars"] < 0.50 and sizing["paper_dollars"] < 1.00:
            log(f"  Skipping {edge.ticker} — suggested bet too small to be meaningful")
            continue

        send_trade_alert(edge, sizing)
        log_alert(edge, sizing)
        auto_bettor.place_auto_bet(api, edge)
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
