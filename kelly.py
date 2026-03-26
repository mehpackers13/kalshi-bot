"""
KELLY CRITERION BET SIZING
===========================
Fractional Kelly with hard caps by edge bucket.
Never recommends more than 5% of bankroll on any single market.
"""

import config
from edge_calculator import EdgeResult
from bankroll import load_bankroll


def kelly_fraction(prob_win: float, odds: float) -> float:
    """
    Classic Kelly formula: f* = (b*p - q) / b
    where b = net odds (profit per $1 risked), p = P(win), q = 1-p.
    For Kalshi YES contracts: b = (1 - price) / price
    """
    q = 1.0 - prob_win
    if odds <= 0:
        return 0.0
    raw_kelly = (odds * prob_win - q) / odds
    return max(0.0, raw_kelly)


def size_bet(edge: EdgeResult) -> dict:
    """
    Return recommended bet size in dollars and contracts for both
    the live ($100) and paper ($1000) bankrolls.
    """
    bankroll = load_bankroll()
    live_bal  = bankroll["live"]["balance"]
    paper_bal = bankroll["paper"]["balance"]

    trade_edge = abs(edge.edge_pct)

    # Hard cap % by edge bucket
    if trade_edge >= 25:
        cap_pct = config.BET_SIZE_STRONG_MAX
    elif trade_edge >= 15:
        cap_pct = config.BET_SIZE_MEDIUM_MAX
    else:
        cap_pct = config.BET_SIZE_SMALL_MAX

    # Kalshi YES contract price for Kelly calculation
    if edge.direction == "YES":
        price_cents = edge.yes_ask   # cost to buy YES
        prob_win    = edge.adjusted_prob
    else:
        # Buying NO: cost = 100 - yes_bid cents
        price_cents = 100 - edge.yes_bid
        prob_win    = 1.0 - edge.adjusted_prob

    price = price_cents / 100.0   # dollars per contract (max $1)
    if price <= 0 or price >= 1:
        return _zero_sizing(edge)

    # Net odds: win (1 - price) per dollar risked
    net_odds = (1.0 - price) / price

    raw_k = kelly_fraction(prob_win, net_odds)
    adj_k = raw_k * config.KELLY_FRACTION   # fractional Kelly

    # Apply hard cap
    final_pct = min(adj_k, cap_pct)

    # Dollar amounts
    live_dollars  = round(live_bal  * final_pct, 2)
    paper_dollars = round(paper_bal * final_pct, 2)

    # Convert to Kalshi contracts (each contract costs price dollars)
    live_contracts  = max(1, int(live_dollars  / price)) if live_dollars  > 0.01 else 0
    paper_contracts = max(1, int(paper_dollars / price)) if paper_dollars > 0.01 else 0

    # Recalculate actual dollar spend (integer contracts)
    live_dollars  = round(live_contracts  * price, 2)
    paper_dollars = round(paper_contracts * price, 2)

    return {
        "direction":         edge.direction,
        "price_cents":       price_cents,
        "kelly_pct":         round(adj_k * 100, 2),
        "capped_pct":        round(final_pct * 100, 2),
        "live_dollars":      live_dollars,
        "live_contracts":    live_contracts,
        "paper_dollars":     paper_dollars,
        "paper_contracts":   paper_contracts,
        "live_balance":      live_bal,
        "paper_balance":     paper_bal,
        "edge_bucket":       "strong" if trade_edge >= 25 else ("medium" if trade_edge >= 15 else "small"),
    }


def _zero_sizing(edge: EdgeResult) -> dict:
    return {
        "direction": edge.direction, "price_cents": 0,
        "kelly_pct": 0.0, "capped_pct": 0.0,
        "live_dollars": 0.0, "live_contracts": 0,
        "paper_dollars": 0.0, "paper_contracts": 0,
        "live_balance": 0.0, "paper_balance": 0.0, "edge_bucket": "none",
    }
