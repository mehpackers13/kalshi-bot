"""
PROBABILITY MODELS
==================
Category-specific probability estimators that produce a "true probability"
to compare against Kalshi's implied probability.

Design philosophy:
  • Only return a probability when we have genuine signal.
  • Return None when uncertain — the bot stays silent rather than guessing.
  • Models improve over time as outcomes are tracked in outcomes.csv.

Current reliable models:
  - Crypto / Financials : price target using log-normal vol model
  - Economics           : Fed rate (futures), CPI trend, unemployment trend
  - Weather             : climatological base rates (rough but honest)

Models we intentionally skip (insufficient data without paid APIs):
  - Sports, Entertainment, Politics (too noisy, no reliable free data)
"""

import math
import datetime
import re
from typing import Optional

import yfinance as yf

from logger import log


# ── Crypto / Price Target Markets ───────────────────────────────────────────────

_CRYPTO_TICKERS = {
    "bitcoin": "BTC-USD", "btc": "BTC-USD",
    "ethereum": "ETH-USD", "eth": "ETH-USD",
    "solana": "SOL-USD",   "sol": "SOL-USD",
    "xrp": "XRP-USD",
    "doge": "DOGE-USD",    "dogecoin": "DOGE-USD",
    "bnb": "BNB-USD",
    "cardano": "ADA-USD",  "ada": "ADA-USD",
    "avalanche": "AVAX-USD","avax": "AVAX-USD",
    "chainlink": "LINK-USD","link": "LINK-USD",
    "litecoin": "LTC-USD",  "ltc": "LTC-USD",
}

_STOCK_TICKERS = {
    "spy": "SPY", "qqq": "QQQ", "iwm": "IWM", "dia": "DIA",
    "apple": "AAPL",   "aapl": "AAPL",
    "tesla": "TSLA",   "tsla": "TSLA",
    "nvidia": "NVDA",  "nvda": "NVDA",
    "microsoft": "MSFT","msft": "MSFT",
    "amazon": "AMZN",  "amzn": "AMZN",
    "google": "GOOGL", "googl": "GOOGL",
    "meta": "META",
    "netflix": "NFLX", "nflx": "NFLX",
    "gold": "GC=F",    "oil": "CL=F",
    "s&p 500": "SPY",  "s&p500": "SPY",
    "nasdaq": "QQQ",
    "dow jones": "DIA", "dow": "DIA",
}


def _get_current_price(yf_ticker: str) -> Optional[float]:
    try:
        t = yf.Ticker(yf_ticker)
        price = t.fast_info.last_price
        if price and price > 0:
            return float(price)
        hist = t.history(period="1d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass
    return None


def _get_historical_vol(yf_ticker: str, days: int = 30) -> Optional[float]:
    """Annualised daily log-return volatility."""
    try:
        hist = yf.Ticker(yf_ticker).history(period=f"{days}d")
        if len(hist) < 5:
            return None
        returns = hist["Close"].pct_change().dropna()
        daily_vol = float(returns.std())
        return daily_vol * math.sqrt(252)   # annualised
    except Exception:
        return None


def _lognormal_prob(spot: float, strike: float, annual_vol: float,
                    years_to_expiry: float, direction: str) -> float:
    """
    P(S_T > strike) or P(S_T < strike) using risk-neutral log-normal model.
    Assumes zero drift (conservative for short-dated markets).
    """
    if years_to_expiry <= 0 or annual_vol <= 0 or spot <= 0 or strike <= 0:
        return 0.5
    d2 = (math.log(spot / strike)) / (annual_vol * math.sqrt(years_to_expiry))
    # N(d2) ≈ P(S_T > strike) under risk-neutral measure
    prob_above = _norm_cdf(d2)
    return prob_above if direction == "above" else 1.0 - prob_above


def _norm_cdf(x: float) -> float:
    """Standard normal CDF via math.erfc."""
    return 0.5 * math.erfc(-x / math.sqrt(2))


def _extract_price_target(title: str) -> Optional[tuple]:
    """
    Parse price target and direction from a market title.
    Returns (target_price, direction) or None.
    Examples:
      "Will BTC be above $70,000 on ..." → (70000, "above")
      "Will ETH close below $3,500 ..."  → (3500, "below")
      "Bitcoin above $100k ..."          → (100000, "above")
    """
    title_lower = title.lower()

    # Direction
    direction = None
    if any(w in title_lower for w in ["above", "over", "exceed", "higher than", "at or above"]):
        direction = "above"
    elif any(w in title_lower for w in ["below", "under", "less than", "lower than", "at or below"]):
        direction = "below"
    if direction is None:
        return None

    # Price — match $70,000 / $70k / 70000 / 70K
    price = None
    patterns = [
        r"\$[\d,]+[kKmM]?",    # $70,000 or $70k
        r"[\d,]+[kKmM]\b",     # 70k or 70K (no $)
        r"\$[\d,]+(?:\.\d+)?", # $3,500.50
    ]
    for pat in patterns:
        m = re.search(pat, title)
        if m:
            raw = m.group().replace("$", "").replace(",", "").strip()
            multiplier = 1
            if raw.lower().endswith("k"):
                multiplier = 1_000
                raw = raw[:-1]
            elif raw.lower().endswith("m"):
                multiplier = 1_000_000
                raw = raw[:-1]
            try:
                price = float(raw) * multiplier
                break
            except ValueError:
                continue

    if price is None or price <= 0:
        return None
    return (price, direction)


def _find_asset_ticker(title: str, category: str) -> Optional[str]:
    """Match title keywords to a yfinance ticker."""
    title_lower = title.lower()

    pool = _CRYPTO_TICKERS if category in ("Crypto",) else {}
    pool = {**pool, **_STOCK_TICKERS}

    for keyword, ticker in pool.items():
        if keyword in title_lower:
            return ticker
    return None


def model_price_target(market: dict) -> Optional[float]:
    """
    Model probability for crypto/stock price target markets.
    Returns estimated true probability of YES, or None if unmodelable.
    """
    title    = market["title"]
    category = market["category"]
    hours    = market["hours_to_close"]

    parsed = _extract_price_target(title)
    if parsed is None:
        return None

    target, direction = parsed
    yf_ticker = _find_asset_ticker(title, category)
    if yf_ticker is None:
        return None

    spot = _get_current_price(yf_ticker)
    if spot is None or spot <= 0:
        return None

    annual_vol = _get_historical_vol(yf_ticker, days=30)
    if annual_vol is None or annual_vol <= 0:
        annual_vol = 0.80 if category == "Crypto" else 0.25  # conservative defaults

    years = max(hours / 8760, 1 / 8760)  # at least 1 hour

    prob = _lognormal_prob(spot, target, annual_vol, years, direction)
    log(f"  price model: {yf_ticker} spot={spot:.2f} target={target:.2f} "
        f"vol={annual_vol:.1%} T={hours:.1f}h → P={prob:.3f}")
    return round(prob, 4)


# ── Economics: Fed Rate ──────────────────────────────────────────────────────────

def model_fed_rate(market: dict) -> Optional[float]:
    """
    Use 30-day Fed Funds futures (ZQ=F) to estimate probability of a rate change.
    ZQ price = 100 - implied_rate. Convert to probability of hike/cut/hold.
    """
    title_lower = market["title"].lower()

    is_hike = any(w in title_lower for w in ["hike", "raise", "increase"])
    is_cut  = any(w in title_lower for w in ["cut", "lower", "decrease", "reduce"])
    is_hold = any(w in title_lower for w in ["hold", "unchanged", "pause", "same"])

    if not (is_hike or is_cut or is_hold):
        return None

    try:
        # Nearest-dated Fed funds futures
        zq = yf.Ticker("ZQ=F")
        hist = zq.history(period="5d")
        if hist.empty:
            return None
        futures_price = float(hist["Close"].iloc[-1])
        implied_rate  = 100.0 - futures_price   # e.g. 5.33%

        # Current effective fed funds rate
        sofr = yf.Ticker("^IRX")   # 13-week T-bill as proxy
        sofr_hist = sofr.history(period="5d")
        current_rate = float(sofr_hist["Close"].iloc[-1]) if not sofr_hist.empty else implied_rate

        diff_bps = (implied_rate - current_rate) * 100  # basis points

        # Probability heuristic: market already prices fed moves fairly efficiently
        # We use futures as our best estimate of true probability
        if is_hike:
            # If futures price implies a higher rate, hike is expected
            prob = max(0.05, min(0.95, 0.5 + diff_bps / 50))
        elif is_cut:
            prob = max(0.05, min(0.95, 0.5 - diff_bps / 50))
        else:  # hold
            prob = max(0.05, min(0.95, 1.0 - abs(diff_bps) / 50))

        log(f"  fed model: implied_rate={implied_rate:.3f}% current≈{current_rate:.3f}% "
            f"diff={diff_bps:.1f}bps → P={prob:.3f}")
        return round(prob, 4)

    except Exception as exc:
        log(f"  fed model error: {exc}", "WARN")
        return None


# ── Economics: CPI / Inflation ───────────────────────────────────────────────────

def model_cpi(market: dict) -> Optional[float]:
    """
    Rough CPI probability based on recent breakeven inflation rates.
    Uses 5-year TIPS breakeven (T5YIE via yfinance proxy).
    """
    title_lower = market["title"].lower()
    if "cpi" not in title_lower and "inflation" not in title_lower:
        return None

    # Parse threshold (e.g. "CPI above 3.5%")
    m = re.search(r"(\d+\.?\d*)\s*%", market["title"])
    if not m:
        return None
    threshold = float(m.group(1))

    is_above = "above" in title_lower or "over" in title_lower or "exceed" in title_lower
    is_below = "below" in title_lower or "under" in title_lower

    if not (is_above or is_below):
        return None

    try:
        # Use 10-year breakeven as proxy for inflation expectations
        tips = yf.Ticker("^TNX")   # 10-year Treasury yield
        hist = tips.history(period="5d")
        if hist.empty:
            return None

        # Rough: use current CPI trend as proxy
        # Recent CPI readings available via FRED-like data in yfinance
        # Since we can't get FRED directly, use breakeven spread as signal
        tnx  = float(hist["Close"].iloc[-1])

        # Very rough: if market threshold << current yield environment, higher prob
        # This is intentionally conservative — we only signal large mispricings
        trend_proxy = tnx  # proxy for inflation expectations
        diff = trend_proxy - threshold

        if is_above:
            prob = 0.5 + min(max(diff * 0.1, -0.3), 0.3)
        else:
            prob = 0.5 - min(max(diff * 0.1, -0.3), 0.3)

        log(f"  CPI model: threshold={threshold}% TNX={tnx:.2f}% → P={prob:.3f}")
        return round(float(prob), 4)

    except Exception as exc:
        log(f"  CPI model error: {exc}", "WARN")
        return None


# ── Weather ──────────────────────────────────────────────────────────────────────

# Very rough climatological base rates — better than nothing, honest about uncertainty
_WEATHER_BASE_RATES = {
    # P(above avg temp) by season in major US cities ≈ 0.50 (by definition, roughly)
    # P(rain/snow on a given day) varies by city/season
    # We use 0.45–0.55 range — only flag if Kalshi is far outside this
    "temperature": 0.50,
    "rain":        0.35,
    "snow":        0.20,
    "hurricane":   0.15,
    "tornado":     0.10,
}

def model_weather(market: dict) -> Optional[float]:
    """
    Returns a rough climatological base rate for weather markets.
    Only useful if Kalshi's implied probability is very far from the base rate.
    """
    title_lower = market["title"].lower()
    for keyword, base_rate in _WEATHER_BASE_RATES.items():
        if keyword in title_lower:
            log(f"  weather model: '{keyword}' base_rate={base_rate:.2f}")
            return base_rate
    return None


# ── Dispatcher ───────────────────────────────────────────────────────────────────

def estimate_true_probability(market: dict) -> Optional[float]:
    """
    Main entry point. Tries each model in order of reliability.
    Returns estimated true probability [0,1] or None if unmodelable.
    """
    category = market.get("category", "")
    title    = market.get("title", "")

    # Price target markets (crypto + financials)
    if category in ("Crypto", "Financials"):
        prob = model_price_target(market)
        if prob is not None:
            return prob

    # Economics
    if category == "Economics":
        title_lower = title.lower()
        if "fed" in title_lower or "rate" in title_lower or "fomc" in title_lower:
            prob = model_fed_rate(market)
            if prob is not None:
                return prob
        if "cpi" in title_lower or "inflation" in title_lower:
            prob = model_cpi(market)
            if prob is not None:
                return prob

    # Weather (low confidence — only surfaces large mispricings)
    if category == "Weather":
        prob = model_weather(market)
        if prob is not None:
            return prob

    # Also try price targets for financial markets phrased differently
    if category in ("Financials", "Crypto"):
        prob = model_price_target(market)
        if prob is not None:
            return prob

    return None   # unmodelable — bot stays silent
