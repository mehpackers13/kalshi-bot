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

import config
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

    # Price — match $70,000 / $70k / 70000 / 70K / bare numbers after above/below
    price = None
    patterns = [
        r"\$[\d,]+[kKmM]?",                                 # $70,000 or $70k
        r"[\d,]+[kKmM]\b",                                  # 70k or 70K (no $)
        r"\$[\d,]+(?:\.\d+)?",                              # $3,500.50
        r"(?:above|below|over|under|exceed|higher than|lower than|at or above|at or below)\s+([\d,]+(?:\.\d+)?)",  # bare number after direction keyword
    ]
    for pat in patterns:
        m = re.search(pat, title, re.IGNORECASE)
        if m:
            # Last pattern captures group 1; others capture full match
            raw = (m.group(1) if m.lastindex else m.group()).replace("$", "").replace(",", "").strip()
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


def _find_asset_ticker(title: str, category: str = "") -> Optional[str]:
    """Match title keywords to a yfinance ticker. Accepts pre-lowercased titles."""
    title_lower = title.lower()
    pool = {**_CRYPTO_TICKERS, **_STOCK_TICKERS}
    for keyword, ticker in pool.items():
        if keyword in title_lower:
            return ticker
    return None


# Kalshi price-series markets we can model, keyed by series-ticker prefix.
# Routing on the series ticker (not loose title keywords) is what keeps
# "Meta headcount above 76,000" from being modeled as META stock at $76k.
# (prefix, yfinance symbol, asset class, annualisation days, vol floor)
_PRICE_SERIES = [
    ("KXNASDAQ100", "^NDX",    "index",     252, 0.12),
    ("KXNASDAQ",    "^NDX",    "index",     252, 0.12),
    ("KXINX",       "^GSPC",   "index",     252, 0.10),
    ("KXDOW",       "^DJI",    "index",     252, 0.10),
    ("KXBRENT",     "BZ=F",    "commodity", 252, 0.20),
    ("KXWTI",       "CL=F",    "commodity", 252, 0.20),
    ("KXGOLD",      "GC=F",    "commodity", 252, 0.12),
    ("KXSILVER",    "SI=F",    "commodity", 252, 0.20),
    ("KXBTC",       "BTC-USD", "crypto",    365, 0.40),
    ("KXETH",       "ETH-USD", "crypto",    365, 0.50),
    ("KXSOL",       "SOL-USD", "crypto",    365, 0.60),
    ("KXXRP",       "XRP-USD", "crypto",    365, 0.60),
    ("KXDOGE",      "DOGE-USD","crypto",    365, 0.70),
    ("KXBNB",       "BNB-USD", "crypto",    365, 0.50),
]

_VOL_CACHE: dict = {}   # {symbol: annual vol} — one fetch per scan, not per market


def _price_series(ticker: str) -> Optional[tuple]:
    """Return (series_suffix, symbol, asset_class, ann_days, vol_floor) or None."""
    head = (ticker or "").upper().split("-", 1)[0]
    for prefix, sym, cls, days, floor in _PRICE_SERIES:     # longest prefixes listed first
        if head.startswith(prefix):
            return head[len(prefix):], sym, cls, days, floor
    return None


def _robust_vol(symbol: str, ann_days: int, floor: float) -> float:
    """
    Annualised vol = max(30d realised, 90d realised, floor).

    The old version used 30 calendar days annualised with sqrt(252) for
    everything — crypto trades 365 days, so that alone understated crypto
    vol ~17%, and one quiet month dragged BTC to 19% (implied is usually
    40-60%). Underestimated vol makes every 'will it touch X' market look
    like a free NO bet. Taking the max of two windows plus a floor keeps
    the model from betting against tails the market correctly prices.
    """
    if symbol in _VOL_CACHE:
        return _VOL_CACHE[symbol]
    vols = [floor]
    try:
        closes = yf.Ticker(symbol).history(period="120d")["Close"].dropna()
        rets = (closes / closes.shift(1)).apply(math.log).dropna()
        for window in (30, 90):
            if len(rets) >= window // 2:
                vols.append(float(rets.tail(window).std()) * math.sqrt(ann_days))
    except Exception:
        pass
    _VOL_CACHE[symbol] = max(vols)
    return _VOL_CACHE[symbol]


def _touch_prob(spot: float, strike: float, vol: float, years: float, direction: str) -> float:
    """
    P(price touches the strike at ANY time before expiry), driftless GBM,
    reflection principle: 2 * P(finishing beyond the strike).
    """
    if direction == "above" and spot >= strike:
        return 0.99
    if direction == "below" and spot <= strike:
        return 0.99
    dist = abs(math.log(strike / spot))
    return min(0.99, 2 * _norm_cdf(-dist / (vol * math.sqrt(years))))


def _terminal_prob(spot: float, strike: float, vol: float, years: float, direction: str) -> float:
    """P(price is beyond the strike AT expiry), risk-neutral log-normal, r~0."""
    sig = vol * math.sqrt(years)
    d2 = (math.log(spot / strike) - 0.5 * sig * sig) / sig
    above = _norm_cdf(d2)
    return above if direction == "above" else 1.0 - above


def model_price_target(market: dict) -> Optional[float]:
    """
    Probability of YES for Kalshi crypto / index / commodity price markets.
    Returns None for anything that isn't a recognised price series —
    company KPI markets (headcount, deliveries, subscribers) are skipped.
    """
    series = _price_series(market.get("ticker", ""))
    if series is None:
        return None
    suffix, symbol, asset_class, ann_days, vol_floor = series

    parsed = _extract_price_target(market["title"])
    if parsed is None:
        return None
    target, direction = parsed

    spot = _get_current_price(symbol)
    if spot is None or spot <= 0 or target <= 0:
        return None
    # Guard against unit mismatches (e.g. an index quoted in different units)
    if not (0.2 < target / spot < 5):
        log(f"  price model: {symbol} spot={spot:.2f} vs target={target:.2f} — "
            f"scale mismatch, skipping", "DEBUG")
        return None

    vol   = _robust_vol(symbol, ann_days, vol_floor)
    years = max(market["hours_to_close"] / 8760, 1 / 8760)

    # MAX / MIN series ("will BTC reach above X by ...") resolve on a touch;
    # everything else ("close price above X on <date>") resolves at expiry.
    is_touch = "MAX" in suffix or "MIN" in suffix
    prob = (_touch_prob if is_touch else _terminal_prob)(spot, target, vol, years, direction)

    log(f"  price model: {symbol} spot={spot:.2f} target={target:.2f} "
        f"{'touch' if is_touch else 'expiry'} vol={vol:.0%} T={market['hours_to_close']:.0f}h "
        f"→ P={prob:.3f}")
    return round(max(0.01, min(0.99, prob)), 4)


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


# ── Weather (wttr.in real forecasts) ─────────────────────────────────────────────
#
# Uses https://wttr.in/{city}?format=j1 — free, no API key, 3-day forecast.
# Temperature probability uses a Gaussian error model:
#   NWS 1-day forecast MAE ≈ 3.5°F, grows ~1.5°F per additional day.
# Precipitation probability uses wttr.in's hourly chanceofrain/chanceofsnow,
#   averaged across the day.

import requests as _req

# Major US cities and their wttr.in query strings (longest match first matters)
_WEATHER_CITIES = {
    "san francisco":  "San+Francisco",
    "oklahoma city":  "Oklahoma+City",
    "salt lake city": "Salt+Lake+City",
    "new york city":  "New+York",
    "new orleans":    "New+Orleans",
    "kansas city":    "Kansas+City",
    "los angeles":    "Los+Angeles",
    "las vegas":      "Las+Vegas",
    "el paso":        "El+Paso",
    "st. louis":      "St+Louis",
    "st louis":       "St+Louis",
    "minneapolis":    "Minneapolis",
    "indianapolis":   "Indianapolis",
    "philadelphia":   "Philadelphia",
    "albuquerque":    "Albuquerque",
    "louisville":     "Louisville",
    "cincinnati":     "Cincinnati",
    "pittsburgh":     "Pittsburgh",
    "sacramento":     "Sacramento",
    "jacksonville":   "Jacksonville",
    "charlotte":      "Charlotte",
    "nashville":      "Nashville",
    "baltimore":      "Baltimore",
    "cleveland":      "Cleveland",
    "milwaukee":      "Milwaukee",
    "memphis":        "Memphis",
    "columbus":       "Columbus",
    "richmond":       "Richmond",
    "hartford":       "Hartford",
    "portland":       "Portland",
    "raleigh":        "Raleigh",
    "atlanta":        "Atlanta",
    "chicago":        "Chicago",
    "seattle":        "Seattle",
    "houston":        "Houston",
    "phoenix":        "Phoenix",
    "orlando":        "Orlando",
    "detroit":        "Detroit",
    "buffalo":        "Buffalo",
    "denver":         "Denver",
    "boston":         "Boston",
    "dallas":         "Dallas",
    "austin":         "Austin",
    "miami":          "Miami",
    "tucson":         "Tucson",
    "albany":         "Albany",
    "boise":          "Boise",
    "nyc":            "New+York",
}

# In-memory cache: city_query → {fetched_at, days}
_wttr_cache: dict = {}
_WTTR_CACHE_TTL = 3600   # re-fetch at most once per hour


def _get_wttr_forecast(city_query: str) -> Optional[list]:
    """
    Fetch 3-day forecast from wttr.in.
    Returns list of dicts: [{date, maxtempF, mintempF, rain_pct, snow_pct}, ...] or None.
    """
    import time as _time
    cached = _wttr_cache.get(city_query)
    if cached and (_time.time() - cached["fetched_at"]) < _WTTR_CACHE_TTL:
        return cached["days"]

    url = f"https://wttr.in/{city_query}?format=j1"
    try:
        resp = _req.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            log(f"  wttr.in {city_query}: HTTP {resp.status_code}", "WARN")
            return None
        data  = resp.json()
        days  = []
        for day in data.get("weather", []):
            hourly   = day.get("hourly", [])
            n        = max(len(hourly), 1)
            avg_rain = sum(int(h.get("chanceofrain", 0)) for h in hourly) / n
            avg_snow = sum(int(h.get("chanceofsnow", 0)) for h in hourly) / n
            days.append({
                "date":     day["date"],
                "maxtempF": int(day["maxtempF"]),
                "mintempF": int(day["mintempF"]),
                "rain_pct": round(avg_rain),
                "snow_pct": round(avg_snow),
            })
        _wttr_cache[city_query] = {"fetched_at": _time.time(), "days": days}
        return days or None
    except Exception as exc:
        log(f"  wttr.in fetch error ({city_query}): {exc}", "WARN")
        return None


def _parse_temp_range(title_lower: str) -> Optional[tuple]:
    """
    Parse temperature condition from title.
    Returns (lo, hi, condition) where condition is "range", "above", or "below".
    Examples:
      "83-84 degrees"         → (83, 84, "range")
      "above 85°F"            → (85, 85, "above")
      "below 60 degrees"      → (60, 60, "below")
      "be in the 83 to 84 range" → (83, 84, "range")
    """
    # Range: "83-84" or "83 to 84" or "83–84"
    m = re.search(r"(\d{1,3})\s*(?:-|–|to)\s*(\d{1,3})\s*(?:degrees?|°[FfCc]?)?", title_lower)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        if 0 <= lo <= 130 and 0 <= hi <= 130 and 0 < (hi - lo) <= 10:
            return (lo, hi, "range")

    # Threshold above
    m = re.search(
        r"(?:above|over|exceed|at or above|more than)\s+(\d{2,3})\s*(?:degrees?|°[FfCc]?)?",
        title_lower,
    )
    if m:
        return (int(m.group(1)), int(m.group(1)), "above")

    # Threshold below
    m = re.search(
        r"(?:below|under|less than|at or below)\s+(\d{2,3})\s*(?:degrees?|°[FfCc]?)?",
        title_lower,
    )
    if m:
        return (int(m.group(1)), int(m.group(1)), "below")

    return None


def _parse_target_date(title_lower: str) -> Optional[datetime.date]:
    """Parse target date from market title. Returns date or None."""
    today = datetime.date.today()
    if "today" in title_lower:
        return today
    if "tomorrow" in title_lower:
        return today + datetime.timedelta(days=1)

    _MONTHS = {
        "january": 1, "jan": 1, "february": 2, "feb": 2,
        "march": 3,   "mar": 3, "april": 4,    "apr": 4,
        "may": 5,     "june": 6, "jun": 6,
        "july": 7,    "jul": 7, "august": 8,   "aug": 8,
        "september": 9, "sep": 9, "sept": 9,
        "october": 10, "oct": 10, "november": 11, "nov": 11,
        "december": 12, "dec": 12,
    }
    for mname, mnum in _MONTHS.items():
        m = re.search(rf"\b{mname}\s+(\d{{1,2}})\b", title_lower)
        if m:
            try:
                d = datetime.date(today.year, mnum, int(m.group(1)))
                if d < today:
                    d = datetime.date(today.year + 1, mnum, int(m.group(1)))
                return d
            except ValueError:
                continue

    # Numeric mm/dd
    m = re.search(r"\b(\d{1,2})/(\d{1,2})\b", title_lower)
    if m:
        try:
            d = datetime.date(today.year, int(m.group(1)), int(m.group(2)))
            if d < today:
                d = datetime.date(today.year + 1, int(m.group(1)), int(m.group(2)))
            return d
        except ValueError:
            pass
    return None


def _temp_range_prob(forecast_f: float, lo: float, hi: float, days_out: int) -> float:
    """
    P(actual max temp ∈ [lo, hi]) given a forecast of forecast_f.
    Uses Gaussian error: σ = 3.5°F for 1-day forecast + 1.5°F per additional day.
    We add ±0.5°F to the range boundaries to account for rounding in market titles.
    """
    sigma = 3.5 + max(0, days_out - 1) * 1.5
    prob  = (_norm_cdf((hi + 0.5 - forecast_f) / sigma)
             - _norm_cdf((lo - 0.5 - forecast_f) / sigma))
    return max(0.01, min(0.99, prob))


def _temp_threshold_prob(forecast_f: float, threshold: float,
                         direction: str, days_out: int) -> float:
    """P(max temp above/below threshold) given forecast."""
    sigma = 3.5 + max(0, days_out - 1) * 1.5
    z     = (threshold - forecast_f) / sigma
    if direction == "above":
        return max(0.01, min(0.99, 1.0 - _norm_cdf(z)))
    return max(0.01, min(0.99, _norm_cdf(z)))


def model_weather(market: dict) -> Optional[float]:
    """
    Returns real weather probability using wttr.in 3-day forecasts.
    Parses city, date, and condition type from market title.
    Falls back to None (silent skip) if city or condition can't be parsed.
    """
    title_lower = market["title"].lower()

    # Monthly/seasonal totals ("Rain in Chicago in Mar 2026?", "more than 200
    # tornadoes in March") can't be priced from a 3-day forecast — the date
    # parser found no day and fell back to TODAY's forecast, which is how a
    # 4% chance of rain today priced a whole month's rainfall at 4%.
    if re.search(r"\bin (jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?(\s+\d{4})?\s*\??$",
                 title_lower) or "tornado" in title_lower or "hurricane" in title_lower:
        return None

    # ── Find city (longest match wins) ───────────────────────────────────────
    city_query = None
    for keyword in sorted(_WEATHER_CITIES, key=len, reverse=True):
        if keyword in title_lower:
            city_query = _WEATHER_CITIES[keyword]
            city_label = keyword
            break
    if city_query is None:
        return None   # no known city — stay silent

    # ── Fetch forecast ────────────────────────────────────────────────────────
    days = _get_wttr_forecast(city_query)
    if not days:
        return None

    # ── Target date ───────────────────────────────────────────────────────────
    today       = datetime.date.today()
    target_date = _parse_target_date(title_lower) or today
    days_out    = max(0, (target_date - today).days)

    # Match forecast day by date string, fallback to index
    forecast_day = next(
        (d for d in days if d["date"] == target_date.strftime("%Y-%m-%d")),
        days[min(days_out, len(days) - 1)] if days_out < len(days) else None,
    )
    if forecast_day is None:
        log(f"  weather model: {city_label} no forecast for {target_date}", "WARN")
        return None

    # ── Rain / Snow ───────────────────────────────────────────────────────────
    is_rain = any(w in title_lower for w in ("rain", "precipitation", "shower", "wet day"))
    is_snow = any(w in title_lower for w in ("snow", "blizzard", "snowfall", "flurr"))

    if is_rain and not any(w in title_lower for w in ("temp", "degree", "°", "high", "low")):
        prob = round(max(0.02, min(0.98, forecast_day["rain_pct"] / 100.0)), 4)
        log(f"  weather model: {city_label} rain {target_date} forecast={forecast_day['rain_pct']}% → P={prob:.3f}")
        return prob

    if is_snow and not any(w in title_lower for w in ("temp", "degree", "°", "high", "low")):
        prob = round(max(0.02, min(0.98, forecast_day["snow_pct"] / 100.0)), 4)
        log(f"  weather model: {city_label} snow {target_date} forecast={forecast_day['snow_pct']}% → P={prob:.3f}")
        return prob

    # ── Temperature ───────────────────────────────────────────────────────────
    is_temp = any(w in title_lower for w in (
        "temp", "temperature", "high", "low", "degree", "°f", "°c",
        "heat", "cold", "warm", "cool", "hot",
    ))
    if is_temp:
        forecast_max = float(forecast_day["maxtempF"])
        parsed = _parse_temp_range(title_lower)
        if parsed is None:
            log(f"  weather model: {city_label} can't parse temp condition from title")
            return None

        lo, hi, condition = parsed
        effective_days = max(1, days_out)

        if condition == "range":
            prob = _temp_range_prob(forecast_max, lo, hi, effective_days)
            log(f"  weather model: {city_label} max={forecast_max}°F target=[{lo},{hi}]°F "
                f"days_out={days_out} σ={3.5+max(0,effective_days-1)*1.5:.1f}°F → P={prob:.3f}")
        elif condition == "above":
            prob = _temp_threshold_prob(forecast_max, lo, "above", effective_days)
            log(f"  weather model: {city_label} max={forecast_max}°F above {lo}°F → P={prob:.3f}")
        else:
            prob = _temp_threshold_prob(forecast_max, lo, "below", effective_days)
            log(f"  weather model: {city_label} max={forecast_max}°F below {lo}°F → P={prob:.3f}")

        return round(prob, 4)

    return None   # hurricane/tornado/generic — no wttr.in signal, stay silent


# ── Dispatcher ───────────────────────────────────────────────────────────────────

def estimate_true_probability(market: dict) -> Optional[float]:
    """
    Main entry point. Tries each model in order of reliability.
    Routing is title-keyword driven — category is used as a hint only.
    This means the bot can evaluate markets even when Kalshi's API
    returns an empty or unmapped category string.
    Returns estimated true probability [0,1] or None if unmodelable.
    """
    title_lower = market.get("title", "").lower()
    category    = market.get("category", "")

    # ── Sports (moneyline games via ESPN power ratings + log5) ────────────────
    if category == "Sports" or (market.get("ticker","") or "").upper().startswith(
        ("KXNFL","KXNBA","KXMLB","KXNHL","KXUFC","KXMLS","KXEPL","KXENGPL")):
        try:
            import sports_models
            res = sports_models.analyze_market(market)
            if res is not None:
                return res["true_prob"] if res["direction"] == "YES" else 1 - res["true_prob"]
        except Exception as exc:
            # Never let a sports model error crash the whole scan
            pass

    # ── Fed / CPI — disabled until rebuilt (config.ECON_MODELS_ENABLED) ───────
    # Audit 2026-10-20: 23-25% hit rate over 13 distinct markets. The Fed model
    # reads the front-month futures contract regardless of which meeting the
    # market asks about and keyword-matches "hike" vs "hold" (so "hike 0bps"
    # = a hold scored as a hike); the CPI model forecasts from bond breakevens.
    # A proper rebuild needs per-meeting fed funds futures + the Cleveland Fed
    # CPI nowcast.
    if getattr(config, "ECON_MODELS_ENABLED", False):
        if any(w in title_lower for w in ("fed", "fomc", "interest rate", "federal funds")):
            prob = model_fed_rate(market)
            if prob is not None:
                return prob
        if "cpi" in title_lower or "inflation" in title_lower:
            prob = model_cpi(market)
            if prob is not None:
                return prob

    # ── Weather ───────────────────────────────────────────────────────────────
    if any(w in title_lower for w in (
        "temperature", "temp", "rain", "snow", "hurricane", "tornado",
        "weather", "precipitation", "degrees", "°f", "°c", "rainfall",
        "snowfall", "shower", "blizzard",
    )):
        prob = model_weather(market)
        if prob is not None:
            return prob

    # ── Price target (crypto / indices / commodities) ─────────────────────────
    # Routed by Kalshi series ticker — returns None for non-price series.
    if _price_series(market.get("ticker", "")):
        prob = model_price_target(market)
        if prob is not None:
            return prob

    return None   # unmodelable — bot stays silent
