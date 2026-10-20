"""
BACKTEST GRID SEARCH
=====================
Instead of guessing "is 15mph the right wind threshold?" or "should weather
require combos with other signals?", test every reasonable parameter
combination against the historical data and let the numbers pick.

Smart engineering: cache raw ESPN+weather game data ONCE to CSV, then
re-grade the same dataset under thousands of parameter combos in seconds
(no new API calls per combo).

Dimensions swept:
  - wind_mlb_threshold:    [10, 12, 15, 18, 20, 25] mph
  - wind_nfl_threshold:    [10, 12, 15, 18, 20] mph
  - rain_threshold:        [1, 2, 3, 5] mm
  - cold_threshold:        [40, 45, 50] °F
  - require_combo:         [none, cold+wind, rain+cold, wind+rain]
  - edge_pct_cutoff:       [4, 6, 8, 10] % (minimum model-vs-market gap)

Outputs:
  data/grid_cache.csv       — one row per historical game with ESPN+weather
  data/grid_results.csv     — one row per parameter combo with hit_rate/roi/n
  data/grid_top.json        — top 10 configs by expected profit
"""
from __future__ import annotations

import argparse
import csv
import datetime
import itertools
import json
import math
import os
import time
from pathlib import Path
from typing import Optional

import requests
from venues import venue_for

BASE = Path(__file__).parent
DATA = BASE / "data"
DATA.mkdir(exist_ok=True)

GRID_CACHE  = DATA / "grid_cache.csv"
GRID_RESULTS= DATA / "grid_results.csv"
GRID_TOP    = DATA / "grid_top.json"

ESPN_SITE = "https://site.api.espn.com/apis/site/v2/sports"
OM_HIST   = "https://archive-api.open-meteo.com/v1/archive"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36")

LEAGUES = {"nfl": ("football","nfl"), "mlb": ("baseball","mlb")}
LEAGUE_AVG_TOTAL = {"nfl": 44.5, "mlb": 8.7}


# ── Cache building ─────────────────────────────────────────────────────────
def _get(url: str, params: dict = None) -> Optional[dict]:
    try:
        r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def _fetch_weather(lat: float, lon: float, date_str: str) -> Optional[dict]:
    data = _get(OM_HIST, params={
        "latitude":  lat, "longitude": lon,
        "start_date": date_str, "end_date": date_str,
        "daily":   "temperature_2m_mean,wind_speed_10m_max,precipitation_sum",
        "wind_speed_unit":  "mph",
        "temperature_unit": "fahrenheit",
        "timezone": "America/New_York",
    })
    if not data:
        return None
    daily = data.get("daily") or {}
    try:
        return {
            "wind_mph":  float((daily.get("wind_speed_10m_max")  or [None])[0] or 0),
            "precip_mm": float((daily.get("precipitation_sum")   or [None])[0] or 0),
            "temp_f":    float((daily.get("temperature_2m_mean") or [None])[0] or 70),
        }
    except Exception:
        return None


def _parse_rec(side: dict) -> Optional[float]:
    for rec in (side.get("records") or []):
        if rec.get("type") == "total":
            parts = (rec.get("summary") or "").split("-")
            if len(parts) >= 2:
                try:
                    w, l = int(parts[0]), int(parts[1])
                    if w + l > 0:
                        return w / (w + l)
                except Exception:
                    pass
    return None


def build_cache(leagues: list, start: str, end: str) -> int:
    """Fetch every completed game + weather, write one row per game."""
    rows_out = []
    for lg in leagues:
        sport, lg_code = LEAGUES[lg]
        print(f"\n[{lg}] fetching games {start}..{end}")
        d = datetime.date.fromisoformat(start)
        end_d = datetime.date.fromisoformat(end)
        n_games = 0
        while d <= end_d:
            data = _get(f"{ESPN_SITE}/{sport}/{lg_code}/scoreboard",
                        params={"dates": d.strftime("%Y%m%d"), "limit": 1000})
            if data:
                for ev in data.get("events", []):
                    comp = (ev.get("competitions") or [{}])[0]
                    status = (comp.get("status") or {}).get("type", {})
                    if not status.get("completed"):
                        continue
                    comps = comp.get("competitors", []) or []
                    if len(comps) != 2:
                        continue
                    home = next((c for c in comps if c.get("homeAway")=="home"), None)
                    away = next((c for c in comps if c.get("homeAway")=="away"), None)
                    if not home or not away:
                        continue
                    try:
                        hs, as_ = float(home.get("score") or 0), float(away.get("score") or 0)
                    except Exception:
                        continue
                    home_name = (home.get("team") or {}).get("displayName","")
                    away_name = (away.get("team") or {}).get("displayName","")
                    if not home_name or not away_name:
                        continue
                    venue = venue_for(home_name)
                    wx = {}
                    if venue and not venue.get("indoor"):
                        wx = _fetch_weather(venue["lat"], venue["lon"], d.isoformat()) or {}
                    rows_out.append({
                        "date": d.isoformat(), "league": lg,
                        "home": home_name, "away": away_name,
                        "home_score": hs, "away_score": as_,
                        "total": hs + as_,
                        "home_wp": _parse_rec(home) or "",
                        "away_wp": _parse_rec(away) or "",
                        "outdoor": 1 if (venue and not venue.get("indoor")) else 0,
                        "wind_mph":  wx.get("wind_mph", ""),
                        "precip_mm": wx.get("precip_mm", ""),
                        "temp_f":    wx.get("temp_f", ""),
                    })
                    n_games += 1
            if n_games % 100 == 0 and n_games:
                print(f"  cached {n_games} {lg} games (through {d})")
            d += datetime.timedelta(days=1)
        print(f"  [{lg}] total cached: {n_games}")

    keys = ["date","league","home","away","home_score","away_score","total",
            "home_wp","away_wp","outdoor","wind_mph","precip_mm","temp_f"]
    with open(GRID_CACHE, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows_out:
            w.writerow(r)
    print(f"\n✓ wrote {GRID_CACHE} ({len(rows_out)} rows)")
    return len(rows_out)


# ── Grid search over cached data ───────────────────────────────────────────
def _load_cache() -> list:
    if not GRID_CACHE.exists():
        return []
    rows = []
    with open(GRID_CACHE) as f:
        for r in csv.DictReader(f):
            for k in ("home_score","away_score","total","home_wp","away_wp",
                      "wind_mph","precip_mm","temp_f","outdoor"):
                v = r.get(k, "")
                try: r[k] = float(v) if v not in ("","None",None) else None
                except: r[k] = None
            rows.append(r)
    return rows


def _p_from_z(z: float) -> float:
    return round(2*(1 - 0.5*(1 + math.erf(abs(z)/math.sqrt(2)))), 4)


def _grade_weather_combo(rows: list, params: dict) -> dict:
    """Simulate weather_edge betting under one parameter combo."""
    hits = n = pl = risked = 0
    for r in rows:
        if not r.get("outdoor"):
            continue
        lg   = r["league"]
        wind = r.get("wind_mph") or 0
        rain = r.get("precip_mm") or 0
        temp = r.get("temp_f") or 70
        total = r.get("total")
        if total is None:
            continue

        trigger = False
        if lg == "nfl" and wind > params["wind_nfl"]:
            trigger = True
        if lg == "mlb":
            if wind > params["wind_mlb"]:   trigger = True
            elif rain > params["rain"]:     trigger = True
            elif temp < params["cold"]:     trigger = True

        # Combo requirement
        combo = params.get("require_combo", "none")
        if trigger and combo != "none":
            cold_ok = temp < params["cold"]
            rain_ok = rain > params["rain"]
            wind_ok = wind > (params["wind_mlb"] if lg=="mlb" else params["wind_nfl"])
            if combo == "cold+wind" and not (cold_ok and wind_ok):
                trigger = False
            elif combo == "rain+cold" and not (rain_ok and cold_ok):
                trigger = False
            elif combo == "wind+rain" and not (wind_ok and rain_ok):
                trigger = False

        if not trigger:
            continue

        line = LEAGUE_AVG_TOTAL[lg]
        hit  = 1 if total < line else 0
        n       += 1
        hits    += hit
        risked  += 10.0
        # payout at kalshi_~0 vig, 50¢ price, net odds 1
        pl += (10.0 * 0.99) if hit else -10.0

    hr = hits/n if n else 0.0
    se = math.sqrt(0.25/n) if n else 1.0
    z  = (hr - 0.5)/se if n else 0.0
    return {
        "n": n, "hits": hits,
        "hit_rate": round(hr, 4),
        "roi":      round(pl/risked*100, 2) if risked else 0.0,
        "pl":       round(pl, 2),
        "z":        round(z, 3),
        "p":        _p_from_z(z) if n else 1.0,
    }


def grid_search(rows: list) -> list:
    """Return all parameter combinations evaluated."""
    param_space = {
        "wind_mlb":  [10, 12, 15, 18, 20, 25],
        "wind_nfl":  [10, 12, 15, 18, 20],
        "rain":      [1, 2, 3, 5],
        "cold":      [40, 45, 50],
        "require_combo": ["none", "cold+wind", "rain+cold", "wind+rain"],
    }
    keys = list(param_space.keys())
    results = []
    combos = list(itertools.product(*[param_space[k] for k in keys]))
    print(f"\n[grid] evaluating {len(combos)} parameter combinations against {len(rows)} games...")
    t0 = time.time()
    for vals in combos:
        params = dict(zip(keys, vals))
        res = _grade_weather_combo(rows, params)
        results.append({**params, **res})
    print(f"[grid] done in {time.time()-t0:.1f}s")
    return results


# ── Report ─────────────────────────────────────────────────────────────────
def print_top(results: list, top_n: int = 15) -> list:
    # Rank: expected profit = pl, filtered to combos with n ≥ 100 (significance)
    strong = [r for r in results if r["n"] >= 100]
    strong.sort(key=lambda r: (r["pl"], -r["p"]), reverse=True)
    top = strong[:top_n]

    print("\n" + "="*90)
    print(f"  TOP {len(top)} CONFIGS (n>=100 for significance)")
    print("="*90)
    header = f"  {'wind_mlb':8} {'wind_nfl':8} {'rain':5} {'cold':5} {'combo':12} {'n':5} {'hit%':6} {'ROI%':7} {'pl':8} {'z':6} {'p':6}"
    print(header)
    print("  " + "-"*len(header))
    for r in top:
        print(f"  {r['wind_mlb']:>8} {r['wind_nfl']:>8} {r['rain']:>5} {r['cold']:>5}"
              f"  {r['require_combo']:12} {r['n']:>5}  {r['hit_rate']*100:>5.1f}%"
              f"  {r['roi']:>+6.1f}%  {r['pl']:>+7.2f}  {r['z']:>+5.2f}  {r['p']:>5.3f}")
    return top


def save_results(all_results: list, top: list) -> None:
    with open(GRID_RESULTS, "w", newline="") as f:
        keys = ["wind_mlb","wind_nfl","rain","cold","require_combo",
                "n","hits","hit_rate","roi","pl","z","p"]
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in all_results:
            w.writerow({k: r.get(k,"") for k in keys})
    with open(GRID_TOP, "w") as f:
        json.dump(top, f, indent=2)
    print(f"\n✓ wrote {GRID_RESULTS} ({len(all_results)} combos) and {GRID_TOP}")


# ── CLI ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--rebuild-cache", action="store_true",
                   help="Fetch ESPN+weather fresh (slow, ~20 min)")
    p.add_argument("--start",   default="2024-04-01")
    p.add_argument("--end",     default="2024-10-31")
    p.add_argument("--leagues", default="nfl,mlb")
    args = p.parse_args()

    if args.rebuild_cache or not GRID_CACHE.exists():
        build_cache(args.leagues.split(","), args.start, args.end)

    rows = _load_cache()
    print(f"[cache] loaded {len(rows)} games")
    results = grid_search(rows)
    top = print_top(results)
    save_results(results, top)
