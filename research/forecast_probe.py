"""A/B check: for open KXHIGH/KXLOWT markets, show YES mid, ensemble p_hit, and what each rule would enter.
Run from the repo root:  python3 research/forecast_probe.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from kalshi_api import KalshiAPI                                  # noqa: E402
from rules import weather_tail, weather_forecast                  # noqa: E402


def main():
    api = KalshiAPI()
    ms = weather_tail.fetch_by_series(api, ("KXHIGH", "KXLOWT"))
    ctx = {"api": api, "markets": ms, "by_series": {}, "now": None, "state": {}}
    tail = {e["ticker"] for e in weather_tail.select(ctx)}
    fc = {e["ticker"]: e for e in weather_forecast.select(ctx)}
    print(f"{'ticker':34} {'yes_mid':>7} {'p_hit':>6}  tail  fcst  notes")
    n = 0
    for m in sorted(ms, key=lambda x: x["ticker"]):
        mid = (m["yes_bid"] + m["yes_ask"]) / 2
        if not (2 <= mid <= 30) or m["ticker"].startswith("KXLOWTPERIOD"):
            continue
        a = weather_forecast.assess(m)
        n += 1
        print(f"{m['ticker']:34} {mid:6.1f}c {'' if a is None else format(a[0], '.2f'):>6}  "
              f"{'Y' if m['ticker'] in tail else '-':4}  {'Y' if m['ticker'] in fc else '-':4}  "
              f"{'' if a is None else 'ens %d/%d in %s (mean %.1f) h=%.0f' % (a[1], a[2], a[4], a[3], m['hours_to_close'])}")
    print(f"\n{n} tail-priced (2-30c) markets; weather_tail would enter {len(tail)} (KXHIGH only, 6-36h); "
          f"weather_tail_forecast would enter {len(fc)} (KXHIGH+KXLOWT, 6-36h)")


if __name__ == "__main__":
    main()
