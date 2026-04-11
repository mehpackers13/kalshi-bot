"""
AUTO-BETTING ENGINE
===================
Stage 2: automatic order placement via Kalshi API.

Flow for each edge found during a scan:
  1. Safety checks (drawdown stop, hourly rate limit, dry-run flag)
  2. Size the bet at 50% Kelly, hard-capped at 5% of live balance
  3. Place limit order via API (or log as dry-run)
  4. Write row to bets_placed.csv
  5. Send Discord notification to #kalshi-signals

Safety rules:
  • DRY_RUN = True in config.py prevents any real orders (default)
  • Never more than MAX_AUTO_BETS_PER_HOUR real bets per hour
  • Auto-pause and urgent Discord alert if balance drops 40% below peak
  • Bot resumes when live_stopped flag is manually cleared in bankroll.json

To go live: set DRY_RUN = False in config.py
To resume after drawdown pause: set "live_stopped": false in data/bankroll.json
"""

import csv
import datetime
import uuid
from typing import Optional

import requests

import config
from edge_calculator import EdgeResult
from bankroll import load_bankroll, save_bankroll
from logger import log


# ── CSV schema ────────────────────────────────────────────────────────────────

_CSV_HEADERS = [
    "timestamp", "ticker", "title", "category",
    "direction", "contracts", "price_cents", "dollars_risked",
    "edge_pct", "true_prob", "implied_prob", "confidence",
    "kelly_fraction", "dry_run", "order_id", "status",
]


# ── Rate-limit helpers ────────────────────────────────────────────────────────

def _count_real_bets_last_hour() -> int:
    """Count non-dry-run bets placed in the last 60 minutes."""
    if not config.BETS_PLACED_CSV.exists():
        return 0
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(hours=1)
    count  = 0
    try:
        with open(config.BETS_PLACED_CSV, newline="") as f:
            for row in csv.DictReader(f):
                if row.get("dry_run", "True").lower() == "true":
                    continue
                try:
                    ts = datetime.datetime.fromisoformat(row["timestamp"])
                    if ts > cutoff:
                        count += 1
                except Exception:
                    pass
    except Exception:
        pass
    return count


# ── CSV logging ───────────────────────────────────────────────────────────────

def _log_bet_row(row: dict) -> None:
    exists = config.BETS_PLACED_CSV.exists()
    with open(config.BETS_PLACED_CSV, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_CSV_HEADERS)
        if not exists:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in _CSV_HEADERS})


# ── Discord notifications ─────────────────────────────────────────────────────

def _send_bet_notification(edge: EdgeResult, contracts: int, price_cents: int,
                            dollars: float, order_id: str, dry_run: bool) -> None:
    webhook = config.DISCORD_SIGNALS_WEBHOOK
    if not webhook:
        return

    mode_tag = "🔵 DRY RUN" if dry_run else "✅ AUTO-BET PLACED"
    color    = 0x5865F2 if dry_run else 0x57F287
    dir_emoji = "🟢" if edge.direction == "YES" else "🔴"
    sign     = "+" if edge.edge_pct > 0 else ""

    embed = {
        "title":       f"{mode_tag} — {edge.category}",
        "description": edge.title[:200],
        "color":       color,
        "fields": [
            {"name": "Direction",   "value": f"{dir_emoji} **{edge.direction}**", "inline": True},
            {"name": "Contracts",   "value": str(contracts),                       "inline": True},
            {"name": "Price",       "value": f"{price_cents}¢/contract",           "inline": True},
            {"name": "Amount",      "value": f"**${dollars:.2f}**",               "inline": True},
            {"name": "Edge",        "value": f"{sign}{edge.edge_pct:.1f}%",        "inline": True},
            {"name": "Confidence",  "value": f"{edge.confidence}/100",             "inline": True},
            {"name": "Model Prob",  "value": f"{edge.true_prob:.1%}",              "inline": True},
            {"name": "Market Prob", "value": f"{edge.implied_prob:.1%}",           "inline": True},
            {"name": "Ticker",      "value": f"`{edge.ticker}`",                   "inline": True},
        ],
        "footer": {"text": f"{edge.reasoning[:150]}"},
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }
    if order_id:
        embed["fields"].append(
            {"name": "Order ID", "value": f"`{order_id}`", "inline": False}
        )

    try:
        requests.post(webhook, json={"embeds": [embed]}, timeout=10)
    except Exception as exc:
        log(f"Discord bet notification failed: {exc}", "WARN")


def _send_drawdown_alert(br: dict) -> None:
    webhook = config.DISCORD_HEALTH_WEBHOOK or config.DISCORD_SIGNALS_WEBHOOK
    if not webhook:
        return
    live    = br.get("live", {})
    balance = live.get("balance", 0)
    peak    = live.get("peak", 1)
    drop    = (peak - balance) / peak * 100 if peak > 0 else 0
    embed = {
        "title":       "🚨 AUTO-BET PAUSED — DRAWDOWN ALERT",
        "description": (
            f"Live balance has dropped **{drop:.1f}%** below peak.\n\n"
            f"**Peak:** ${peak:.2f}  →  **Current:** ${balance:.2f}\n\n"
            f"Auto-betting is **PAUSED**. To resume:\n"
            f"Set `\"live_stopped\": false` in `data/bankroll.json` and push to GitHub."
        ),
        "color":     0xED4245,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }
    try:
        requests.post(webhook, json={"embeds": [embed]}, timeout=10)
    except Exception as exc:
        log(f"Drawdown alert failed: {exc}", "WARN")


# ── Open position value ───────────────────────────────────────────────────────

def _get_open_position_value(api) -> float:
    """
    Estimate current market value of all open positions at bid prices.
    Used for exposure limit enforcement.
    """
    try:
        positions = api.get_portfolio_positions()
        total = 0.0
        for pos in positions:
            count_fp = float(pos.get("position_fp") or pos.get("position") or 0)
            if count_fp == 0:
                continue
            # Try market_exposure first
            for key in ("market_exposure_fp", "market_exposure"):
                raw = pos.get(key)
                if raw is not None:
                    val = float(raw)
                    if abs(val) > 10:
                        val /= 100
                    total += abs(val)
                    break
            else:
                # Fallback using prices stored on the position
                if count_fp > 0:
                    bid = float(pos.get("yes_bid_dollars") or 0)
                    if bid > 1:
                        bid /= 100
                    total += count_fp * bid
                else:
                    ask = float(pos.get("yes_ask_dollars") or 0)
                    if ask > 1:
                        ask /= 100
                    total += abs(count_fp) * max(0.0, 1.0 - ask)
        return round(total, 2)
    except Exception as exc:
        log(f"Could not calculate open position value: {exc}", "WARN")
        return 0.0


# ── Cut-loss logic ────────────────────────────────────────────────────────────

def _send_cut_loss_notification(ticker: str, side: str, count: int,
                                 entry_cents: int, current_cents: int,
                                 loss_pct: float, order_id: str) -> None:
    webhook = config.DISCORD_SIGNALS_WEBHOOK
    if not webhook:
        return
    embed = {
        "title":       f"✂️ CUT LOSS — {ticker}",
        "description": "Position sold to prevent further losses.",
        "color":       0xFEE75C,
        "fields": [
            {"name": "Side",        "value": side.upper(),      "inline": True},
            {"name": "Contracts",   "value": str(count),         "inline": True},
            {"name": "Entry Price", "value": f"{entry_cents}¢",  "inline": True},
            {"name": "Exit Price",  "value": f"{current_cents}¢","inline": True},
            {"name": "Loss",        "value": f"{loss_pct:.0%}",  "inline": True},
            {"name": "Order ID",    "value": f"`{order_id}`",    "inline": False},
        ],
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }
    try:
        requests.post(webhook, json={"embeds": [embed]}, timeout=10)
    except Exception as exc:
        log(f"Cut loss notification failed: {exc}", "WARN")


def cut_losing_positions(api) -> list:
    """
    Scan open positions for ones that have lost ≥60% of entry value AND
    have more than 48 hours until expiry.  Sell those positions to cut losses.

    Near-expiry positions (<48h) are left alone — they'll either recover or
    resolve, and selling into thin end-of-life markets locks in max loss.

    Returns list of tickers that were sold (or attempted).
    """
    if config.DRY_RUN:
        return []

    # Build lookup: ticker → {price_cents, direction} from bets_placed.csv
    entry_info: dict = {}
    if config.BETS_PLACED_CSV.exists():
        try:
            with open(config.BETS_PLACED_CSV, newline="") as f:
                for row in csv.DictReader(f):
                    ticker = row.get("ticker", "")
                    if ticker and ticker not in entry_info:
                        try:
                            entry_info[ticker] = {
                                "price_cents": int(row.get("price_cents") or 0),
                                "direction":   row.get("direction", "YES").upper(),
                            }
                        except Exception:
                            pass
        except Exception:
            pass

    positions = api.get_portfolio_positions()
    cut: list = []

    for pos in positions:
        ticker   = pos.get("ticker", "")
        count_fp = float(pos.get("position_fp") or pos.get("position") or 0)
        if not ticker or count_fp == 0:
            continue

        info = entry_info.get(ticker)
        if not info or not info["price_cents"]:
            continue   # no entry record — can't calculate loss

        entry_cents = info["price_cents"]
        direction   = info["direction"]   # "YES" or "NO"

        # Fetch current market to get price + close time
        market = api.get_market(ticker)
        if not market:
            continue

        # Current sell price (bid side — what we'd actually receive)
        if direction == "YES":
            bid_raw     = float(market.get("yes_bid_dollars") or
                                market.get("yes_bid", 0) or 0)
            current_cents = int(round(bid_raw * 100 if bid_raw <= 1 else bid_raw))
            sell_side     = "yes"
            sell_yes_price = current_cents
        else:
            ask_raw    = float(market.get("yes_ask_dollars") or
                               market.get("yes_ask", 0) or 0)
            yes_ask_cents = int(round(ask_raw * 100 if ask_raw <= 1 else ask_raw))
            current_cents  = max(0, 100 - yes_ask_cents)   # current NO bid
            sell_side      = "no"
            sell_yes_price = yes_ask_cents   # sell NO → yes_price = YES ask

        if current_cents <= 0 or entry_cents <= 0:
            continue

        loss_pct = (entry_cents - current_cents) / entry_cents
        if loss_pct < config.CUT_LOSS_PCT:
            continue   # loss not large enough

        # Check hours remaining until expiry
        close_str = market.get("close_time") or market.get("expiration_time", "")
        hours_left = 9999.0
        if close_str:
            try:
                import datetime as _dt
                close_dt   = _dt.datetime.fromisoformat(close_str.replace("Z", "+00:00"))
                hours_left = (close_dt - _dt.datetime.now(_dt.timezone.utc)).total_seconds() / 3600
            except Exception:
                pass

        if hours_left <= config.CUT_LOSS_MIN_HOURS:
            log(
                f"CUT LOSS SKIP {ticker}: {loss_pct:.0%} loss but only "
                f"{hours_left:.0f}h left — letting it ride",
                "DEBUG",
            )
            continue

        # Sell
        n = max(1, int(abs(count_fp)))
        log(
            f"CUT LOSS: {ticker} {direction} {n}ct — entry {entry_cents}¢ → "
            f"current {current_cents}¢ = {loss_pct:.0%} loss, {hours_left:.0f}h to expiry",
            "WARN",
        )
        try:
            result   = api.sell_position(
                ticker=ticker, side=sell_side, count=n, yes_price=sell_yes_price
            )
            order_id = result.get("order", {}).get("order_id", "?")
            log(f"CUT LOSS ✅ {ticker}: sold {n}ct @ {current_cents}¢ | order={order_id}")
            _send_cut_loss_notification(
                ticker, direction, n, entry_cents, current_cents, loss_pct, order_id
            )
            cut.append(ticker)
        except Exception as exc:
            log(f"CUT LOSS ERROR {ticker}: {exc}", "ERROR")

    return cut


# ── Bet sizing (50% Kelly, 5% hard cap) ──────────────────────────────────────

def _size_auto_bet(edge: EdgeResult, live_balance: float) -> dict:
    """
    50% fractional Kelly, hard-capped at AUTO_BET_MAX_PCT of live balance.
    Returns {side, yes_price, contracts, price_cents, dollars}.
    """
    if edge.direction == "YES":
        price_cents = edge.yes_ask
        side        = "yes"
        prob_win    = edge.adjusted_prob
    else:
        price_cents = 100 - edge.yes_bid
        side        = "no"
        prob_win    = 1.0 - edge.adjusted_prob

    if price_cents <= 0 or price_cents >= 100:
        return {}

    price = price_cents / 100.0
    # Kelly: f* = (b*p - q) / b  where b = net_odds = (1-price)/price
    net_odds  = (1.0 - price) / price
    q         = 1.0 - prob_win
    raw_kelly = max(0.0, (net_odds * prob_win - q) / net_odds)

    # Apply 50% Kelly fraction, then hard cap at 5%
    adj_kelly  = raw_kelly * config.AUTO_BET_KELLY_FRACTION
    capped_pct = min(adj_kelly, config.AUTO_BET_MAX_PCT)

    dollars   = round(live_balance * capped_pct, 2)
    contracts = max(1, int(dollars / price))
    actual_cost = round(contracts * price, 2)

    return {
        "side":        side,
        "yes_price":   price_cents if side == "yes" else (100 - price_cents),
        "price_cents": price_cents,
        "contracts":   contracts,
        "dollars":     actual_cost,
        "kelly_pct":   round(adj_kelly * 100, 2),
        "capped_pct":  round(capped_pct * 100, 2),
    }


# ── Main entry point ──────────────────────────────────────────────────────────

def place_auto_bet(api, edge: EdgeResult) -> dict:
    """
    Attempt to auto-place a bet for an edge opportunity.
    Performs all safety checks before submitting.
    Returns result dict: {placed, reason, dry_run, ...}
    """
    dry_run  = config.DRY_RUN
    br       = load_bankroll()

    # ── Safety check 1: drawdown stop ──────────────────────────────────────
    if br.get("live_stopped"):
        log("AUTO-BET BLOCKED: drawdown stop active — reset live_stopped in bankroll.json", "WARN")
        return {"placed": False, "reason": "drawdown_stop"}

    live_balance = br.get("live", {}).get("balance", 0)
    peak         = br.get("live", {}).get("peak", 0)

    if not dry_run and peak > 0 and live_balance < peak * (1.0 - config.DRAWDOWN_STOP_PCT):
        # Trigger stop and alert
        br["live_stopped"] = True
        save_bankroll(br)
        _send_drawdown_alert(br)
        log(
            f"AUTO-BET PAUSED: balance ${live_balance:.2f} dropped "
            f"{config.DRAWDOWN_STOP_PCT:.0%}+ below peak ${peak:.2f}",
            "WARN",
        )
        return {"placed": False, "reason": "drawdown_triggered"}

    # ── Safety check 2: hourly rate limit ──────────────────────────────────
    if not dry_run:
        hourly = _count_real_bets_last_hour()
        if hourly >= config.MAX_AUTO_BETS_PER_HOUR:
            log(
                f"AUTO-BET RATE LIMIT: {hourly}/{config.MAX_AUTO_BETS_PER_HOUR} bets "
                f"placed this hour — skipping {edge.ticker}",
                "WARN",
            )
            return {"placed": False, "reason": "rate_limit"}

    # ── Safety check 3: maximum exposure (25% of total account) ────────────
    if not dry_run:
        position_value = _get_open_position_value(api)
        total_value    = live_balance + position_value
        if total_value > 0:
            exposure_pct = position_value / total_value
            if exposure_pct >= config.MAX_EXPOSURE_PCT:
                log(
                    f"AUTO-BET SKIP {edge.ticker}: exposure {exposure_pct:.1%} ≥ "
                    f"{config.MAX_EXPOSURE_PCT:.0%} limit "
                    f"(${position_value:.2f} of ${total_value:.2f} in open positions)",
                    "WARN",
                )
                return {"placed": False, "reason": "max_exposure"}

    # ── Sizing ──────────────────────────────────────────────────────────────
    sizing = _size_auto_bet(edge, live_balance if live_balance > 0 else 10.0)
    if not sizing or sizing.get("dollars", 0) < 0.50:
        log(f"AUTO-BET SKIP {edge.ticker}: bet too small (<$0.50)", "DEBUG")
        return {"placed": False, "reason": "too_small"}

    side        = sizing["side"]
    yes_price   = sizing["yes_price"]
    price_cents = sizing["price_cents"]
    contracts   = sizing["contracts"]
    dollars     = sizing["dollars"]

    # ── Place order (or simulate) ───────────────────────────────────────────
    order_id = ""
    status   = "dry_run" if dry_run else "pending"

    if not dry_run:
        try:
            result   = api.place_order(
                ticker    = edge.ticker,
                side      = side,
                count     = contracts,
                yes_price = yes_price,
            )
            order    = result.get("order", {})
            order_id = order.get("order_id", "")
            status   = order.get("status", "submitted")
            log(
                f"AUTO-BET ✅ {edge.ticker} {edge.direction} {contracts}ct "
                f"@ {price_cents}¢ = ${dollars:.2f} | order={order_id} | "
                f"edge={edge.edge_pct:+.1f}% conf={edge.confidence}",
                "INFO",
            )
        except Exception as exc:
            log(f"AUTO-BET ERROR {edge.ticker}: {exc}", "ERROR")
            _log_bet_row({
                "timestamp":    datetime.datetime.utcnow().isoformat(),
                "ticker":       edge.ticker,
                "title":        edge.title[:80],
                "category":     edge.category,
                "direction":    edge.direction,
                "contracts":    contracts,
                "price_cents":  price_cents,
                "dollars_risked": dollars,
                "edge_pct":     round(edge.edge_pct, 2),
                "true_prob":    round(edge.true_prob, 4),
                "implied_prob": round(edge.implied_prob, 4),
                "confidence":   edge.confidence,
                "kelly_fraction": config.AUTO_BET_KELLY_FRACTION,
                "dry_run":      False,
                "order_id":     "",
                "status":       f"error: {str(exc)[:100]}",
            })
            return {"placed": False, "reason": str(exc)}
    else:
        log(
            f"DRY RUN 🔵 {edge.ticker} {edge.direction} {contracts}ct "
            f"@ {price_cents}¢ = ${dollars:.2f} | edge={edge.edge_pct:+.1f}% "
            f"conf={edge.confidence} | would_use {config.AUTO_BET_KELLY_FRACTION*100:.0f}%Kelly",
            "INFO",
        )

    # ── Log to CSV ──────────────────────────────────────────────────────────
    _log_bet_row({
        "timestamp":     datetime.datetime.utcnow().isoformat(),
        "ticker":        edge.ticker,
        "title":         edge.title[:80],
        "category":      edge.category,
        "direction":     edge.direction,
        "contracts":     contracts,
        "price_cents":   price_cents,
        "dollars_risked": dollars,
        "edge_pct":      round(edge.edge_pct, 2),
        "true_prob":     round(edge.true_prob, 4),
        "implied_prob":  round(edge.implied_prob, 4),
        "confidence":    edge.confidence,
        "kelly_fraction": config.AUTO_BET_KELLY_FRACTION,
        "dry_run":       dry_run,
        "order_id":      order_id,
        "status":        status,
    })

    # ── Discord notification ────────────────────────────────────────────────
    _send_bet_notification(edge, contracts, price_cents, dollars, order_id, dry_run)

    return {
        "placed":    True,
        "dry_run":   dry_run,
        "contracts": contracts,
        "price_cents": price_cents,
        "dollars":   dollars,
        "order_id":  order_id,
        "status":    status,
    }
