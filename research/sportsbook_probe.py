"""
Probe: how much of Kalshi's sports book can be priced from the free ESPN/DraftKings feed?

Prints
  1. per league: ESPN events (ET today..+2), events with DK game odds, prop lines fetched
  2. over/under pair-order check (is the first unlabeled item really the OVER?)
  3. per Kalshi sports series closing <= 7 days: markets seen / matched / unmatched-by-reason
     and the match rate rolled up by market type
  4. top 20 gaps (edge after fee, any size) between Kalshi executable price and devigged book
  5. prop_projection: rule output + projection-vs-book calibration on shared lines

Run from the repo root:  python3 research/sportsbook_probe.py
Read-only: public Kalshi GETs and public ESPN GETs only.
"""
from __future__ import annotations

import datetime
import math
import os
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import requests  # noqa: E402

import kalshi_api  # noqa: E402
import sports_match as sm  # noqa: E402
import sportsbook as sb  # noqa: E402

KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
HDR = {"User-Agent": "Mozilla/5.0"}


def fetch_series(series):
    out, cur = [], None
    for _ in range(8):
        p = {"series_ticker": series, "status": "open", "limit": 1000}
        if cur:
            p["cursor"] = cur
        try:
            r = requests.get(f"{KALSHI}/markets", params=p, headers=HDR, timeout=30).json()
        except Exception:
            break
        out += r.get("markets", [])
        cur = r.get("cursor")
        if not cur:
            break
    return series, out


def main():
    sb.reset_budget(700)   # the probe is allowed more than a scan (a scan is capped at 250)
    now = datetime.datetime.utcnow()
    today = sb.to_eastern_date(now)

    print("=" * 78)
    print("1. ESPN / DraftKings coverage (ET %s .. +2 days)" % today)
    print("%-11s %7s %7s %9s %11s" % ("league", "events", "pre", "w/ odds", "prop lines"))
    sb.prefetch_scoreboards({(lg, today + datetime.timedelta(days=i)) for lg in sb.LEAGUES for i in range(0, 3)})
    evs_by = {lg: [e for i in range(0, 3) for e in sb.get_scoreboard(lg, today + datetime.timedelta(days=i))]
              for lg in sb.LEAGUES}
    allpre = [e for lst in evs_by.values() for e in lst if e["state"] == "pre"]
    sb.prefetch_odds(allpre)
    pro = [e for e in allpre if sb.LEAGUES[e["league"]][3]]
    # props for events that have game odds (otherwise the feed is not live yet)
    with_odds = [e for e in pro if sb.load_game_odds(e)]
    sb.prefetch_props(with_odds)
    tot_lines = 0
    for lg, lst in evs_by.items():
        pre = [e for e in lst if e["state"] == "pre"]
        wo = [e for e in pre if sb.load_game_odds(e)]
        lines = 0
        for e in wo:
            if sb.LEAGUES[lg][3]:
                p = sb.load_props(e)
                lines += len(p) if p else 0
        tot_lines += lines
        print("%-11s %7d %7d %9d %11d" % (lg, len(lst), len(pre), len(wo), lines))
    print("ESPN calls so far: %d   prop lines fetched: %d" % (sb.calls_used(), tot_lines))

    print("\n" + "=" * 78)
    print("2. Over/under pair order check (first item = over?) vs milestone ladder of same player")
    ok = bad = skipped = 0
    pairs = {"Total Points": "Points Milestones", "Total Rebounds": "Rebounds Milestones",
             "Total Assists": "Assists Milestones", "Total Receiving Yards (incl. overtime)": "Receiving Yards Milestones",
             "Total Rushing Yards (incl. overtime)": "Rushing Yards Milestones",
             "Total Passing Yards (incl. overtime)": "Passing Yards Milestones"}
    for e in with_odds:
        props = sb.load_props(e) or []
        lad = defaultdict(list)
        for r in props:
            if r["shape"] == "milestone":
                lad[(r["type"], r["aid"])].append((r["line"], sb.am_to_prob(r["am"])))
        for r in props:
            if r["shape"] != "pair" or r["type"] not in pairs:
                continue
            m = sorted(lad.get((pairs[r["type"]], r["aid"]), []))
            k = math.ceil(r["line"])
            lo = [x for x in m if x[0] <= k]
            hi = [x for x in m if x[0] >= k]
            if not lo or not hi:
                skipped += 1
                continue
            a0, a1 = lo[-1], hi[0]
            pl = a0[1] if a1[0] == a0[0] else a0[1] + (a1[1] - a0[1]) * (k - a0[0]) / (a1[0] - a0[0])
            d = sb.devig_two(r["am"], r["am_other"])
            if d is None or abs(d[0] - 0.5) < 0.01:
                skipped += 1
                continue
            if abs(d[0] - pl) < abs(1 - d[0] - pl):
                ok += 1
            else:
                bad += 1
    print("first-item-is-over consistent: %d   inconsistent: %d   skipped(no ladder/coin-flip): %d  -> %.0f%% consistent"
          % (ok, bad, skipped, 100.0 * ok / max(1, ok + bad)))

    print("\n" + "=" * 78)
    print("3. Kalshi sports series closing <= 7 days: match rates")
    series = sorted(sm.SERIES)
    with ThreadPoolExecutor(max_workers=8) as ex:
        fetched = dict(ex.map(fetch_series, series))
    markets = []
    for s, rows in fetched.items():
        for raw in rows:
            m = kalshi_api.parse_market(raw)
            if not m:
                continue
            try:
                ct = datetime.datetime.strptime(m["close_time"][:19], "%Y-%m-%dT%H:%M:%S")
            except Exception:
                continue
            h = (ct - now).total_seconds() / 3600.0
            if 0 < h <= 168:
                m["hours_to_close"] = h
                markets.append(m)
    print("open sports markets in %d known series closing <=7d (with a usable quote): %d" % (len(series), len(markets)))
    sm.STATS.clear()
    sm.REASONS.clear()
    per_series = defaultdict(Counter)
    orig = sm._count

    cur = [None]

    def spy(mt, reason):
        per_series[cur[0]][reason] += 1
        return orig(mt, reason)

    sm._count = spy
    sm.prepare(markets)
    matches = []
    for m in markets:
        cur[0] = m["series"]
        r = sm.match(m)
        if r:
            matches.append((m, r))
    sm._count = orig
    print("ESPN calls used: %d" % sb.calls_used())
    print("\n%-26s %6s %7s  %s" % ("series", "seen", "matched", "unmatched by reason"))
    for s in sorted(per_series, key=lambda x: -sum(per_series[x].values())):
        c = per_series[s]
        seen = sum(c.values())
        rs = ", ".join("%s=%d" % kv for kv in c.most_common() if kv[0] != "matched")
        print("%-26s %6d %7d  %s" % (s, seen, c.get("matched", 0), rs))
    print("\nmatch rate by market type")
    for mt, o in sorted(sm.summary().items(), key=lambda kv: -kv[1]["total"]):
        print("  %-11s seen %5d  matched %5d  rate %5.1f%%   %s" % (
            mt, o["total"], o["matched"], 100 * o["rate"],
            ", ".join("%s=%d" % kv for kv in sorted(o["reasons"].items(), key=lambda kv: -kv[1]))))
    sb.save_athletes()

    print("\n" + "=" * 78)
    print("4. Top 20 gaps (edge after taker fee; bid>=1, ask<=99, spread<=10c; game not started)")
    rows = []
    for m, r in matches:
        if r["start"] <= now or m["yes_bid"] < 1 or m["yes_ask"] > 99 or m["yes_ask"] - m["yes_bid"] > 10:
            continue
        bid, ask = m["yes_bid"] / 100.0, m["yes_ask"] / 100.0
        ey = r["p"] - (ask + sm.fee(ask))
        en = (1 - r["p"]) - ((1 - bid) + sm.fee(1 - bid))
        side, e = ("YES", ey) if ey >= en else ("NO", en)
        rows.append((e, side, m, r))
    rows.sort(key=lambda x: -x[0])
    for e, side, m, r in rows[:20]:
        print("%+.3f %-3s %-44s bid/ask %2d/%2d vol %-5.0f %s%s" % (
            e, side, m["ticker"][:44], m["yes_bid"], m["yes_ask"], m.get("volume") or 0, r["desc"][:60],
            " [approx]" if r["approx"] else ""))
    n3 = sum(1 for x in rows if x[0] >= (0.05 if x[3]["approx"] else 0.03))
    print("candidate entries at rule thresholds (3c exact / 5c approx): %d of %d matched+tradable" % (n3, len(rows)))
    print("exact (non-approx) matches: %d, approx: %d" % (sum(1 for _, r in matches if not r["approx"]),
                                                          sum(1 for _, r in matches if r["approx"])))

    print("\n" + "=" * 78)
    print("5. prop_projection (independent of the book)")
    from rules import prop_projection as pp
    from rules import sports_gap as sg
    ctx = {"api": None, "markets": markets, "by_series": {}, "now": now, "state": {}}
    out = pp.select(ctx)
    print("rule output: %d entries; diagnostics %s; skip reasons %s" % (len(out), pp.LAST, dict(pp.REASONS)))
    for e in out[:10]:
        print("  %s %s %s" % (e["ticker"], e["side"], e["notes"]))
    # calibration: projection vs book on identical lines
    diffs = []
    S = pp._load()["players"]
    for m, r in matches:
        if r["mtype"] != "prop":
            continue
        rp = sm.resolve_player(m)
        if not rp:
            continue
        spec = rp["spec"]
        label = pp.LABEL_MAP.get((rp["league"], spec[0]), spec[0])
        ent = S.get("%s:%s" % (rp["league"], rp["aid"]))
        if not ent or label not in ent.get("s", {}):
            continue
        res = pp.project(ent["s"][label], label, rp["threshold"])
        if res:
            diffs.append((res[0], r["p"]))
    if diffs:
        n = len(diffs)
        md = sum(a - b for a, b in diffs) / n
        ma = sum(abs(a - b) for a, b in diffs) / n
        xa, xb = [a for a, _ in diffs], [b for _, b in diffs]
        mx, my = sum(xa) / n, sum(xb) / n
        cov = sum((a - mx) * (b - my) for a, b in diffs)
        sx = math.sqrt(sum((a - mx) ** 2 for a in xa))
        sy = math.sqrt(sum((b - my) ** 2 for b in xb))
        print("projection vs book on %d shared lines: mean(proj-book)=%+.3f  mean|diff|=%.3f  corr=%.2f"
              % (n, md, ma, cov / (sx * sy) if sx and sy else float("nan")))
    else:
        print("no shared lines with cached stats yet (stats fill 60 players per scan)")
    g = sg.select(ctx)
    print("\nsports_gap rule output: %d entries; %s" % (len(g), sg.LAST))
    for e in g[:10]:
        print("  %s %s %s" % (e["ticker"], e["side"], e["notes"]))
    print("\nTOTAL ESPN calls this run: %d" % sb.calls_used())


if __name__ == "__main__":
    main()
