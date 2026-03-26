"""
EDGE CALCULATOR
===============
Compares Kalshi's implied probability to our model's true probability.
Applies all risk filters and returns a final EdgeResult or None.
"""

import datetime
from dataclasses import dataclass, field
from typing import Optional

import config
from probability_models import estimate_true_probability
from logger import log


@dataclass
class EdgeResult:
    ticker:        str
    title:         str
    category:      str
    implied_prob:  float      # Kalshi market's mid-price probability
    true_prob:     float      # our model's estimate
    edge_pct:      float      # (true_prob - implied_prob) * 100
    direction:     str        # "YES" or "NO"
    confidence:    int        # 0–100 score
    reasoning:     str        # human-readable explanation
    dollar_volume: float
    hours_to_close: float
    yes_bid:       int
    yes_ask:       int
    close_time:    str        = ""
    model_name:    str        = ""
    adjusted_prob: float      = 0.0  # after model confidence adjustment


def _gate_check(market: dict) -> Optional[str]:
    """
    Return a failure reason string if market fails any hard filter.
    Return None if it passes all gates.
    """
    if market["dollar_volume"] < config.MIN_VOLUME_DOLLARS:
        return f"volume ${market['dollar_volume']:.0f} < ${config.MIN_VOLUME_DOLLARS}"
    if market["implied_prob"] < config.MIN_IMPLIED_PROB:
        return f"implied prob {market['implied_prob']:.1%} < {config.MIN_IMPLIED_PROB:.0%}"
    if market["implied_prob"] > config.MAX_IMPLIED_PROB:
        return f"implied prob {market['implied_prob']:.1%} > {config.MAX_IMPLIED_PROB:.0%}"
    if market["hours_to_close"] < config.MIN_HOURS_TO_CLOSE:
        return f"closes in {market['hours_to_close']:.1f}h < {config.MIN_HOURS_TO_CLOSE}h"
    if market["status"] != "open":
        return f"status={market['status']}"
    return None


def _confidence_score(market: dict, edge_pct: float, category: str) -> tuple:
    """
    Return (score 0–100, reasoning string).
    Higher volume, larger edge, modelable category → higher score.
    """
    score = 50   # base

    # Edge size bonus
    if abs(edge_pct) >= 25:
        score += 25
    elif abs(edge_pct) >= 15:
        score += 15
    elif abs(edge_pct) >= 8:
        score += 8

    # Volume bonus
    vol = market["dollar_volume"]
    if vol >= 100_000:
        score += 15
    elif vol >= 25_000:
        score += 10
    elif vol >= 5_000:
        score += 5

    # Time to close — prefer markets with 6+ hours remaining
    hours = market["hours_to_close"]
    if hours >= 24:
        score += 5
    elif hours < 6:
        score -= 10

    # Category reliability penalty
    if category == "Weather":
        score -= 15   # rough base rates only
    if category in ("Crypto",):
        score -= 5    # high vol, model less reliable

    score = max(0, min(100, score))

    parts = []
    if abs(edge_pct) >= 15:
        parts.append(f"strong edge ({edge_pct:+.1f}%)")
    elif abs(edge_pct) >= 8:
        parts.append(f"moderate edge ({edge_pct:+.1f}%)")
    if vol >= 25_000:
        parts.append(f"good volume (${vol:,.0f})")
    if hours >= 24:
        parts.append("plenty of time remaining")
    if category == "Weather":
        parts.append("rough climatological model")

    reasoning = "; ".join(parts) if parts else f"edge {edge_pct:+.1f}%"
    return score, reasoning


def calculate_edge(market: dict) -> Optional[EdgeResult]:
    """
    Full pipeline: filter → model → edge → confidence.
    Returns EdgeResult if edge >= MIN_EDGE_PCT, else None.
    """
    ticker   = market["ticker"]
    category = market.get("category", "")

    # Hard filter gates
    fail_reason = _gate_check(market)
    if fail_reason:
        return None   # silent — this is normal

    # Probability model
    true_prob = estimate_true_probability(market)
    if true_prob is None:
        return None   # unmodelable — stay silent

    implied_prob = market["implied_prob"]

    # Raw edge: positive means we think YES is underpriced (buy YES)
    raw_edge = (true_prob - implied_prob) * 100   # in percentage points

    # We can trade either side
    if abs(raw_edge) < config.MIN_EDGE_PCT:
        return None   # edge too small — stay silent

    direction = "YES" if raw_edge > 0 else "NO"
    edge_pct  = raw_edge  # signed: +ve = buy YES, -ve = buy NO

    # Adjust true_prob for direction
    # If buying NO, the effective edge is the mirror
    trade_edge_pct = abs(edge_pct)

    confidence, reasoning = _confidence_score(market, edge_pct, category)

    # Apply confidence discount to probability
    # Blend our estimate toward implied prob based on uncertainty
    conf_weight   = confidence / 100.0
    adjusted_prob = conf_weight * true_prob + (1 - conf_weight) * implied_prob

    result = EdgeResult(
        ticker        = ticker,
        title         = market["title"],
        category      = category,
        implied_prob  = implied_prob,
        true_prob     = true_prob,
        adjusted_prob = adjusted_prob,
        edge_pct      = edge_pct,
        direction     = direction,
        confidence    = confidence,
        reasoning     = reasoning,
        dollar_volume = market["dollar_volume"],
        hours_to_close= market["hours_to_close"],
        yes_bid       = market["yes_bid"],
        yes_ask       = market["yes_ask"],
        close_time    = market.get("close_time", ""),
    )

    log(f"  EDGE FOUND: {ticker} | implied={implied_prob:.1%} true={true_prob:.1%} "
        f"edge={edge_pct:+.1f}% dir={direction} conf={confidence}")

    return result
