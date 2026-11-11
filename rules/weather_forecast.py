"""weather_tail_forecast: same universe as weather_tail (KXHIGH*, plus KXLOWT*), but only buy NO when the
Open-Meteo GFS ensemble says the strike is very unlikely (p_hit <= 3%).

Strike formats (confirmed live 2026-11-11), all whole-degree F, settled on the NWS CLI report:
  KXHIGHAUS-26NOV12-B79.5  title "...be 79-80° on..."  yes_sub "79° to 80°"  -> round(max) in [79,80]
  KXHIGHAUS-26NOV12-T80    title "...be >80° on..."    yes_sub "81° or above" -> round(max) >= 81
  KXHIGHAUS-26NOV12-T73    title "...be <73° on..."    yes_sub "72° or below" -> round(max) <= 72
KXLOWT* are identical but for the daily minimum. Members are continuous, so the integer reading is
modelled by +-0.5F: bucket [lo-0.5, hi+0.5), '>X' is x >= X+0.5, '<X' is x < X-0.5.
"""
import datetime
import re
import time

import requests

from logger import log
from rules.weather_tail import MIN_H, MAX_H, MIN_YES, MAX_YES, series_of, universe

NAME = "weather_tail_forecast"
CAP = 150
MAX_P = 0.03
TTL = 20 * 60

# city code (series suffix, a leading T is stripped when needed) -> (name, lat, lon, tz)
# Approximate airport / park coordinates of the CLI station named in each market's rules.
CITIES = {
    "AUS": ("Austin CLIAUS", 30.19, -97.67, "America/Chicago"),
    "CHI": ("Chicago CLIMDW (Midway)", 41.79, -87.75, "America/Chicago"),
    "DEN": ("Denver CLIDEN", 39.86, -104.67, "America/Denver"),
    "LAX": ("Los Angeles CLILAX", 33.94, -118.41, "America/Los_Angeles"),
    "MIA": ("Miami CLIMIA", 25.79, -80.29, "America/New_York"),
    "NY": ("New York City CLINYC (Central Park)", 40.78, -73.97, "America/New_York"),
    "NYC": ("New York City CLINYC (Central Park)", 40.78, -73.97, "America/New_York"),
    "PHIL": ("Philadelphia CLIPHL", 39.87, -75.24, "America/New_York"),
    "ATL": ("Atlanta CLIATL", 33.64, -84.43, "America/New_York"),
    "BOS": ("Boston CLIBOS", 42.36, -71.01, "America/New_York"),
    "DAL": ("Dallas CLIDFW", 32.90, -97.04, "America/Chicago"),
    "DC": ("Washington DC CLIDCA", 38.85, -77.04, "America/New_York"),
    "EWR": ("Newark CLIEWR", 40.69, -74.17, "America/New_York"),
    "HOU": ("Houston CLIHOU (Hobby)", 29.65, -95.28, "America/Chicago"),
    "LV": ("Las Vegas CLILAS", 36.08, -115.15, "America/Los_Angeles"),
    "MIN": ("Minneapolis CLIMSP", 44.88, -93.22, "America/Chicago"),
    "NOLA": ("New Orleans CLIMSY", 29.99, -90.26, "America/Chicago"),
    "OKC": ("Oklahoma City CLIOKC", 35.39, -97.60, "America/Chicago"),
    "PHX": ("Phoenix CLIPHX", 33.43, -112.01, "America/Phoenix"),
    "SAN": ("San Diego CLISAN", 32.73, -117.19, "America/Los_Angeles"),
    "SATX": ("San Antonio CLISAT", 29.53, -98.47, "America/Chicago"),
    "SDF": ("Louisville CLISDF", 38.17, -85.74, "America/New_York"),
    "SEA": ("Seattle CLISEA", 47.45, -122.31, "America/Los_Angeles"),
    "SFO": ("San Francisco CLISFO", 37.62, -122.38, "America/Los_Angeles"),
    "TTN": ("Trenton CLITTN", 40.28, -74.82, "America/New_York"),
}
URL = "https://ensemble-api.open-meteo.com/v1/ensemble"
_MONTHS = {m: i + 1 for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split())}
_CACHE = {}     # code -> (fetched_ts, {"max": {date: [members]}, "min": {...}})


def city_for(series: str):
    """('high'|'low', code, city tuple) or None."""
    if series.startswith("KXHIGH"):
        kind, rest = "max", series[6:]
    elif series.startswith("KXLOWT"):
        kind, rest = "min", series[6:]
    else:
        return None
    for code in (rest, rest[1:] if rest.startswith("T") else None):
        if code and code in CITIES:
            return kind, code, CITIES[code]
    return None


def market_date(ticker: str):
    m = re.match(r"^[A-Z0-9]+-(\d\d)([A-Z]{3})(\d\d)", ticker)
    if not m or m.group(2) not in _MONTHS:
        return None
    return datetime.date(2000 + int(m.group(1)), _MONTHS[m.group(2)], int(m.group(3)))


def strike(m: dict):
    """(lo, hi) continuous bounds in F (None = unbounded) from the title, else from the ticker."""
    title = (m.get("title") or "")
    g = re.search(r"(-?\d+)\s*-\s*(-?\d+)\s*°", title)
    if g:
        return int(g.group(1)) - 0.5, int(g.group(2)) + 0.5
    g = re.search(r">\s*(-?\d+)\s*°", title)
    if g:
        return int(g.group(1)) + 0.5, None
    g = re.search(r"<\s*(-?\d+)\s*°", title)
    if g:
        return None, int(g.group(1)) - 0.5
    g = re.search(r"-B(-?\d+(?:\.\d+)?)$", m["ticker"])
    if g:
        c = float(g.group(1))
        return c - 1.0, c + 1.0
    return None


def members(code: str, kind: str, day: datetime.date):
    """List of ensemble member values (F) for the city/day, cached ~20 min per city."""
    now = time.time()
    hit = _CACHE.get(code)
    if not hit or now - hit[0] > TTL:
        name, lat, lon, tz = CITIES[code]
        try:
            r = requests.get(URL, params={"latitude": lat, "longitude": lon, "models": "gfs_seamless",
                                          "daily": "temperature_2m_max,temperature_2m_min",
                                          "temperature_unit": "fahrenheit", "forecast_days": 4,
                                          "timezone": tz}, timeout=20)
            r.raise_for_status()
            d = r.json().get("daily", {})
            dates = d.get("time", [])
            data = {"max": {}, "min": {}}
            for k, name_k in (("max", "temperature_2m_max"), ("min", "temperature_2m_min")):
                cols = [v for key, v in d.items() if key.startswith(name_k)]
                for i, ds in enumerate(dates):
                    vals = [c[i] for c in cols if i < len(c) and c[i] is not None]
                    data[k][datetime.date.fromisoformat(ds)] = vals
            hit = (now, data)
        except Exception as ex:
            log(f"weather_forecast: ensemble fetch failed for {code}: {ex}", "WARN")
            hit = (now - TTL + 120, {"max": {}, "min": {}})        # retry in ~2 min, not every market
        _CACHE[code] = hit
        time.sleep(0.15)
    return hit[1][kind].get(day) or []


def p_hit(vals: list, bounds):
    lo, hi = bounds
    n = len(vals)
    k = sum(1 for x in vals if (lo is None or x >= lo) and (hi is None or x < hi))
    return k / n, k, n


def assess(m: dict):
    """(p_hit, k, n, mean, label) or None if the market can't be modelled."""
    c = city_for(series_of(m))
    day = market_date(m["ticker"])
    b = strike(m)
    if not c or not day or not b:
        return None
    kind, code, _ = c
    vals = members(code, kind, day)
    if len(vals) < 20:
        return None
    p, k, n = p_hit(vals, b)
    lo, hi = b
    label = (f"{lo + .5:.0f}-{hi - .5:.0f}" if lo is not None and hi is not None
             else (f">{lo - .5:.0f}" if lo is not None else f"<{hi + .5:.0f}"))
    return p, k, n, sum(vals) / n, label


def select(ctx) -> list:
    out, skipped = [], 0
    for m in universe(ctx, ("KXHIGH", "KXLOWT")):
        if m["ticker"].startswith("KXLOWTPERIOD") or not (MIN_H <= m["hours_to_close"] <= MAX_H):
            continue
        yb, ya = m["yes_bid"] / 100.0, m["yes_ask"] / 100.0
        if yb < 0.01 or not (MIN_YES <= (yb + ya) / 2 <= MAX_YES):
            continue
        a = assess(m)
        if a is None:
            skipped += 1
            continue
        p, k, n, mean, label = a
        if p <= MAX_P:
            out.append({"ticker": m["ticker"], "side": "NO", "category": "Climate and Weather",
                        "series": series_of(m), "model_prob": p,
                        "notes": f"ens {k}/{n} in {label} (mean {mean:.1f})"})
    if skipped:
        log(f"{NAME}: {skipped} markets not modellable (unknown city/format/forecast)")
    return out
