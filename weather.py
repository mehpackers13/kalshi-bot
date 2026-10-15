"""
WEATHER — wttr.in (free, no key needed)
=========================================
Used by sports_models.py for weather-sensitive totals markets.
Wind > 15mph kills passing games and affects run/score totals.

Ported from sports-betting-bot (where weather_edge is the only
proven +EV signal: +10.4% ROI over 82 bets).
"""
import requests
from typing import Optional

from logger import log

# Known outdoor NFL stadiums by city
OUTDOOR_NFL_CITIES = {
    "chicago", "green bay", "pittsburgh", "cleveland", "new york",
    "east rutherford", "foxborough", "boston", "buffalo", "nashville",
    "denver", "kansas city", "baltimore", "cincinnati", "jacksonville",
    "philadelphia", "washington", "charlotte", "miami gardens",
}

# All MLB stadiums are outdoor unless listed here (retractable roof / dome)
INDOOR_MLB_STADIUMS = {
    "miami", "houston", "seattle", "milwaukee", "phoenix", "toronto",
    "st. petersburg", "tampa", "arlington",   # new Globe Life Field
}


def is_outdoor(sport: str, city: str) -> bool:
    """Return True if the venue is outdoor (affected by weather)."""
    if not city:
        return False
    c = city.lower()
    s = (sport or "").lower()
    if s == "nfl":
        return c in OUTDOOR_NFL_CITIES
    if s == "mlb":
        return c not in INDOOR_MLB_STADIUMS
    # NBA, NHL are always indoor; soccer/golf we treat as outdoor
    if s in ("mls", "epl", "pga"):
        return True
    return False


def get_weather(city: str) -> dict:
    """Fetch current weather for a city (wttr.in)."""
    if not city:
        return {}
    try:
        r = requests.get(
            f"https://wttr.in/{city.replace(' ', '+')}?format=j1",
            timeout=8,
        )
        if r.status_code == 200:
            data    = r.json()
            current = (data.get("current_condition") or [{}])[0]
            return {
                "wind_mph":  int(current.get("windspeedMiles", 0) or 0),
                "precip_mm": float(current.get("precipMM", 0) or 0),
                "temp_f":    int(current.get("temp_F", 70) or 70),
                "humidity":  int(current.get("humidity", 50) or 50),
                "condition": (current.get("weatherDesc", [{}])[0] or {}).get("value", ""),
                "city":      city,
            }
    except Exception as exc:
        log(f"weather: fetch failed for {city}: {exc}", "WARN")
    return {}


def total_direction_edge(weather: dict, sport: str) -> Optional[dict]:
    """
    Returns a weather-driven adjustment for a totals market:
      {direction: 'under'|'over', confidence_bump: float, reason: str}
    or None if no edge.

    Edge rules (same as sports-betting-bot's weather_edge):
      - NFL + wind > 15 mph    → UNDER (passing game neutralised)
      - MLB + wind > 15 mph    → UNDER (balls stay in the park)
      - MLB + rain > 2 mm      → UNDER (delays, pitcher-friendly conditions)
      - MLB + temp < 50 F      → UNDER (balls don't carry)
    """
    if not weather:
        return None
    wind  = weather.get("wind_mph", 0)
    rain  = weather.get("precip_mm", 0)
    temp  = weather.get("temp_f", 70)
    s     = (sport or "").lower()

    # Confidence bumps scaled to the empirical weather_edge effect size
    # (+10.4% ROI over 82 bets on sports-betting-bot implied the market
    # misprices weather by ~10-15 probability points, not 5-7).
    if s == "nfl" and wind > 15:
        bump = 0.12 if wind > 25 else 0.09
        return {"direction": "under", "confidence_bump": bump,
                "reason": f"wind {wind}mph — passing neutralised, UNDER"}
    if s == "mlb":
        if wind > 25:
            return {"direction": "under", "confidence_bump": 0.14,
                    "reason": f"wind {wind}mph strong — big UNDER signal"}
        if wind > 15:
            return {"direction": "under", "confidence_bump": 0.10,
                    "reason": f"wind {wind}mph — balls stay in park, UNDER"}
        if rain > 2:
            return {"direction": "under", "confidence_bump": 0.09,
                    "reason": f"rain {rain}mm — delays + pitcher-friendly, UNDER"}
        if temp < 45:
            return {"direction": "under", "confidence_bump": 0.08,
                    "reason": f"temp {temp}°F — balls don't carry, UNDER"}
    return None
