"""
ENSEMBLE ANALYSIS
=================
Reads the completed 2024 backtest games CSV and finds games where
MULTIPLE signals fired on the same game. Measures whether those
'double-signal' bets have higher hit rate than solo signals — the
test of whether ensemble gating would improve ROI.

Rationale: a single weather_edge bet is +EV at 53.8% hit. If also
log5_moneyline fires on the same game (independently predicting an
outcome that correlates with the under), the compound bet should have
higher hit rate but fire less often — classic volume-for-accuracy
trade.
"""
import csv
from pathlib import Path
from collections import defaultdict

BASE = Path(__file__).parent
GAMES_CSV = BASE / "data" / "backtest_games_mlb_nfl_2024.csv"


def analyze():
    if not GAMES_CSV.exists():
        print(f"missing: {GAMES_CSV}")
        return

    with open(GAMES_CSV) as f:
        rows = list(csv.DictReader(f))

    # Group by game key = (date, away, home)
    by_game = defaultdict(list)
    for r in rows:
        key = (r["date"], r["away"], r["home"])
        by_game[key].append(r)

    solo_weather = []
    solo_log5    = []
    combo_both   = []     # weather AND log5 fired on same game

    for key, trades in by_game.items():
        sigs = {t["signal"]: t for t in trades}
        w = sigs.get("weather_edge_under")
        m = sigs.get("log5_moneyline")
        if w and m:
            combo_both.append((w, m))
        elif w:
            solo_weather.append(w)
        elif m:
            solo_log5.append(m)

    def stats(trades, label, hit_key="hit"):
        n = len(trades)
        if n == 0: return
        hits = sum(int(t[hit_key]) for t in trades)
        pl   = sum(float(t["pl"])  for t in trades)
        print(f"  {label:28} n={n:>5}  hits={hits:>4}  "
              f"hit_rate={100*hits/n:>5.1f}%  pl={pl:+8.2f}")

    print("="*70)
    print("  ENSEMBLE ANALYSIS — 2024 MLB+NFL backtest")
    print("="*70)
    stats(solo_weather, "solo weather_edge_under")
    stats(solo_log5,    "solo log5_moneyline")

    # For "combo" we count the HIT only when BOTH legs would have hit.
    # (That's how a 2-leg parlay works.)
    combo_hits = sum(1 for w,m in combo_both if int(w["hit"]) and int(m["hit"]))
    combo_n    = len(combo_both)
    if combo_n:
        print(f"  {'combo (both signals, both hit)':28} n={combo_n:>5}  "
              f"hits={combo_hits:>4}  hit_rate={100*combo_hits/combo_n:>5.1f}%")

    # What if we filter: only bet weather_edge when log5 ALSO fires on same game?
    print()
    print("  Alt filter: 'bet weather_edge ONLY when log5 also fires on this game'")
    aligned_w_hits = sum(int(w["hit"]) for w,m in combo_both)
    if combo_n:
        print(f"    weather_edge hits (when log5 also fires): {aligned_w_hits}/{combo_n} = {100*aligned_w_hits/combo_n:.1f}%")

    # Reverse — bet log5 only when weather also fires
    aligned_m_hits = sum(int(m["hit"]) for w,m in combo_both)
    if combo_n:
        print(f"    log5_moneyline hits (when weather also fires): {aligned_m_hits}/{combo_n} = {100*aligned_m_hits/combo_n:.1f}%")


if __name__ == "__main__":
    analyze()
