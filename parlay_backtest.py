"""
PARLAY BACKTEST
================
Takes the already-graded 2024 backtest games and simulates the parlay
strategy: for every game where both weather_edge AND log5_moneyline
fired, treat as a 2-leg parlay, compute hit (both must hit), compute
payout at compound-price.

Also tests 3-leg combos: group same-day same-sport games with signals,
simulate 3-leg parlays.

No new API calls — just re-grades the existing CSV under parlay rules.
"""
import csv
import math
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).parent
GAMES_CSV = BASE / "data" / "backtest_games_mlb_nfl_2024.csv"

# Realistic Kalshi prices for weather_edge legs (NO/under) and log5 legs
# (YES or NO on side chosen). In backtest we don't have real market prices,
# so we assume ~50¢ (fair-market baseline) for each leg.
LEG_PRICE = 0.50


def _parse_rows() -> list:
    with open(GAMES_CSV) as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["hit"] = int(r["hit"])
    return rows


def _p_z(z: float) -> float:
    return round(2*(1 - 0.5*(1 + math.erf(abs(z)/math.sqrt(2)))), 4)


def simulate_2leg_same_game(rows: list) -> dict:
    """2-leg parlay: both signals fire on the same game → parlay those two."""
    by_game = defaultdict(dict)
    for r in rows:
        key = (r["date"], r["away"], r["home"])
        by_game[key][r["signal"]] = r

    parlays = []
    for key, sigs in by_game.items():
        if len(sigs) < 2:
            continue
        legs = list(sigs.values())
        if len(legs) < 2:
            continue
        # 2-leg: both must hit
        both_hit = all(l["hit"] for l in legs[:2])
        payout_mult = (1.0 / (LEG_PRICE ** 2))   # fair 2-leg at 50¢ each = 4.0 (3:1 net odds)
        stake  = 1.0
        pl     = stake * (payout_mult - 1) if both_hit else -stake
        parlays.append({"legs": 2, "hit": int(both_hit), "pl": pl,
                        "legs_detail": [l["signal"] for l in legs[:2]]})
    return _summarize("2-leg same-game", parlays)


def simulate_2leg_same_signal_same_day(rows: list, signal: str) -> dict:
    """2-leg parlay: two games same day both have this signal firing."""
    by_date = defaultdict(list)
    for r in rows:
        if r["signal"] == signal:
            by_date[r["date"]].append(r)
    parlays = []
    for date, bets in by_date.items():
        bets = sorted(bets, key=lambda b: b["home"])
        for i in range(0, len(bets)-1, 2):
            a, b = bets[i], bets[i+1]
            both_hit = a["hit"] and b["hit"]
            payout_mult = 1.0 / (LEG_PRICE ** 2)
            stake  = 1.0
            pl     = stake * (payout_mult - 1) if both_hit else -stake
            parlays.append({"legs": 2, "hit": int(both_hit), "pl": pl,
                            "legs_detail": [signal, signal]})
    return _summarize(f"2-leg same-signal same-day ({signal})", parlays)


def simulate_3leg_same_signal_same_day(rows: list, signal: str) -> dict:
    by_date = defaultdict(list)
    for r in rows:
        if r["signal"] == signal:
            by_date[r["date"]].append(r)
    parlays = []
    for date, bets in by_date.items():
        bets = sorted(bets, key=lambda b: b["home"])
        for i in range(0, len(bets)-2, 3):
            a, b, c = bets[i], bets[i+1], bets[i+2]
            all_hit = a["hit"] and b["hit"] and c["hit"]
            payout_mult = 1.0 / (LEG_PRICE ** 3)   # 8x at 50¢ legs
            stake  = 1.0
            pl     = stake * (payout_mult - 1) if all_hit else -stake
            parlays.append({"legs": 3, "hit": int(all_hit), "pl": pl,
                            "legs_detail": [signal]*3})
    return _summarize(f"3-leg same-signal same-day ({signal})", parlays)


def _summarize(label: str, parlays: list) -> dict:
    n = len(parlays)
    if n == 0:
        return {"label": label, "n": 0, "note": "no parlays triggered"}
    hits = sum(p["hit"] for p in parlays)
    pl   = sum(p["pl"]  for p in parlays)
    hr   = hits/n
    se   = math.sqrt(0.25/n)
    z    = (hr - 0.5)/se
    return {
        "label": label,
        "n": n, "hits": hits,
        "hit_rate": round(hr, 4),
        "pl_per_unit_stake": round(pl, 2),
        "roi_pct": round(pl/n * 100, 2),
        "z": round(z, 3),
        "p": _p_z(z),
    }


def main():
    rows = _parse_rows()
    print(f"Loaded {len(rows)} graded single-bet rows\n")

    runs = [
        simulate_2leg_same_game(rows),
        simulate_2leg_same_signal_same_day(rows, "log5_moneyline"),
        simulate_2leg_same_signal_same_day(rows, "weather_edge_under"),
        simulate_3leg_same_signal_same_day(rows, "log5_moneyline"),
        simulate_3leg_same_signal_same_day(rows, "weather_edge_under"),
    ]
    print("="*85)
    print(f"  {'strategy':50} {'n':>5} {'hits':>5} {'hit%':>6} {'ROI%':>7} {'z':>6}  {'p':>6}")
    print("="*85)
    for r in runs:
        if r.get("n") == 0:
            print(f"  {r['label']:50} —  no parlays triggered")
            continue
        print(f"  {r['label']:50} {r['n']:>5} {r['hits']:>5} "
              f"{r['hit_rate']*100:>5.1f}% {r['roi_pct']:>+6.1f}% "
              f"{r['z']:>+5.2f}  {r['p']:>5.3f}")


if __name__ == "__main__":
    main()
