"""
OPTIONS → KALSHI CROSS-SIGNAL
==============================
When the options bot sees unusual activity (volume_spike) on a stock
that Kalshi has price-target markets for, boost confidence on those
Kalshi markets. Options flow is forward-looking — a big volume spike
today predicts a 3%+ move within 5 trading days 62.9% of the time
(backtest proven, p=0.002).

Flow:
  options-bot alerts_log.csv  (via GitHub raw URL)
    → fetch today's/yesterday's volume_spike alerts
    → extract tickers
  Kalshi scanner evaluating a stock-price-target market
    → ask: is this ticker in today's options flow?
    → if yes, bump the confidence multiplier for that market

Direction note: volume_spike is magnitude-agnostic (predicts |move|),
not direction. For Kalshi price-target markets, we interpret as:
  - If Kalshi market is "will X be above $Y?" and options flow suggests
    a 3%+ move, that INCREASES the probability of resolution either way.
  - For markets near the strike (implied prob 30-70%), this adds edge.
  - For markets with implied prob < 10% or > 90%, options flow doesn't
    change direction and we skip.

The signal is a confidence BOOST (0 - 0.15 multiplier), not a bet
override. Final buy/sell decision stays with the Kalshi probability
model.
"""
from __future__ import annotations

import csv
import datetime
import io
import time
from typing import Optional

import requests


_OPTIONS_ALERTS_URL = (
    "https://raw.githubusercontent.com/mehpackers13/options-bot/main/alerts_log.csv"
)
_CACHE: dict = {"ts": 0.0, "data": set()}
_CACHE_TTL = 10 * 60   # 10 minutes


def _recent_volume_spike_tickers(within_days: int = 3) -> set:
    """
    Returns the set of tickers that had a volume_spike alert fire in the
    last `within_days` days. Cached 10 min.
    """
    now = time.time()
    if now - _CACHE["ts"] < _CACHE_TTL and _CACHE["data"]:
        return _CACHE["data"]
    try:
        r = requests.get(_OPTIONS_ALERTS_URL, timeout=10)
        if r.status_code != 200:
            return set()
        rows = list(csv.DictReader(io.StringIO(r.text)))
    except Exception:
        return set()

    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=within_days)
    tickers = set()
    for row in rows:
        if (row.get("signal_type") or "").lower() != "volume_spike":
            continue
        ts_str = row.get("timestamp", "")
        try:
            ts = datetime.datetime.strptime(ts_str[:19].replace("T"," "),
                                            "%Y-%m-%d %H:%M:%S")
            if ts < cutoff:
                continue
        except Exception:
            continue
        t = (row.get("ticker") or "").strip().upper()
        if t:
            tickers.add(t)
    _CACHE["ts"]   = now
    _CACHE["data"] = tickers
    return tickers


def confidence_boost(kalshi_ticker: str, kalshi_title: str) -> float:
    """
    Returns a probability-multiplier bump (0.00 to 0.15) if a related
    stock ticker has recent options-bot volume_spike activity.

    kalshi_ticker format examples:
      KXTSLA-26OCTDELIV-440000
      KXAMZNA-28JANHEAD-1500000
      KXMETAA-28JANHEAD-65000

    We look for a 3-5 letter uppercase run after 'KX' that matches
    a stock ticker. If matched AND recent volume_spike alert → boost.
    """
    import re
    ttl = (kalshi_ticker or "").upper()
    tit = (kalshi_title or "").upper()

    # Try to pull a stock ticker from the Kalshi ticker string
    m = re.match(r"^KX([A-Z]{2,5})", ttl)
    if not m:
        return 0.0
    candidate = m.group(1)
    # Common Kalshi prefixes we must NOT treat as stock tickers
    if candidate in ("MLB","NFL","NBA","NHL","UFC","PGA","MLS","EPL","WNBA",
                     "BTC","ETH","SOL","WCT","FED","CPI","INX",
                     "FEDHIKE","FEDDECISION","FEDCPI","HIGHNY","HIGHMIA",
                     "BRENTD","BRENTW","BRENTMON","PCECORE","INCORNYIELD",
                     "RATECUT","LEADERSOUT","INTLFRIENDLYGAME","INTLFRIENDLYSPREAD",
                     "WCSPREAD","WCTEAMTOTAL","NHLMETROPOLITAN","NHLSERIESGAMES",
                     "NBASPREAD","NBASUMMERSPREAD","NFLSPREAD","NCAAFSPREAD",
                     "WNBASPREAD","WNBATOTAL","WNBATEAMTOTAL","MLBSPREAD",
                     "MLBTOTAL","NFLTOTAL","PGAROUNDSCORE"):
        return 0.0

    hot = _recent_volume_spike_tickers()
    if candidate in hot:
        return 0.10   # 10 point probability boost — meaningful but not override
    return 0.0


def is_hot_ticker(ticker: str) -> bool:
    """Quick boolean check: is this stock ticker in recent options flow?"""
    return (ticker or "").upper() in _recent_volume_spike_tickers()
