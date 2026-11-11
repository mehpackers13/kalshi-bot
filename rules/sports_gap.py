"""
sports_gap: Kalshi sports price vs devigged DraftKings reference (via ESPN).

p_book = devigged probability of the Kalshi YES outcome (sports_match.match()).
  edge_yes = p_book - (yes_ask + fee(yes_ask))
  edge_no  = (1 - p_book) - ((1 - yes_bid) + fee(1 - yes_bid))
Enter the better side when edge >= 0.03 (0.05 when the book price was one-sided / order-inferred,
flagged approx).  Needs yes_bid >= 1, yes_ask <= 99 and spread <= 10c.  Only games that have not
started (ESPN state 'pre') are ever matched.  model_prob = p_book (probability that YES wins,
for either side).  Max 4 entries per event so one game cannot fill the cap (strike ladders on a
single event are one outcome for the statistics).
"""
from __future__ import annotations

import datetime

import sports_match as sm
import sportsbook as sb

NAME = "sports_gap"
CAP = 40
MIN_EDGE = 0.03
MIN_EDGE_APPROX = 0.05
MAX_SPREAD_C = 10
MAX_HOURS = 168
PER_EVENT = 4
LAST = {}   # diagnostics for the probe / scan_diag


def select(ctx) -> list:
    now = ctx.get("now") or datetime.datetime.utcnow()
    cands = [m for m in ctx["markets"]
             if m.get("series") in sm.SERIES and 0 < (m.get("hours_to_close") or 0) <= MAX_HOURS
             and m.get("yes_bid", 0) >= 1 and m.get("yes_ask", 100) <= 99
             and (m["yes_ask"] - m["yes_bid"]) <= MAX_SPREAD_C]
    LAST.clear()
    LAST["candidates"] = len(cands)
    if not cands:
        return []
    sm.prepare(cands)
    out = []
    matched = 0
    for m in cands:
        r = sm.match(m)
        if not r:
            continue
        if r["start"] <= now + datetime.timedelta(minutes=5):
            continue
        matched += 1
        bid, ask = m["yes_bid"] / 100.0, m["yes_ask"] / 100.0
        p = r["p"]
        e_yes = p - (ask + sm.fee(ask))
        e_no = (1 - p) - ((1 - bid) + sm.fee(1 - bid))
        thr = MIN_EDGE_APPROX if r["approx"] else MIN_EDGE
        side, edge = ("YES", e_yes) if e_yes >= e_no else ("NO", e_no)
        if edge < thr:
            continue
        thin = (m.get("volume") or 0) < 20
        notes = f"{r['desc']} | edge {edge:.3f}{' | approx' if r['approx'] else ''}{' | thin' if thin else ''}"
        out.append({"ticker": m["ticker"], "side": side, "category": m.get("category") or "Sports",
                    "event": m.get("event") or "-".join(m["ticker"].split("-")[:2]),
                    "series": m.get("series"), "model_prob": round(p, 4),
                    "notes": notes[:120].replace(",", ";"), "_edge": edge})
    out.sort(key=lambda e: -e["_edge"])
    per, final = {}, []
    for e in out:
        n = per.get(e["event"], 0)
        if n >= PER_EVENT:
            continue
        per[e["event"]] = n + 1
        final.append(e)
        if len(final) >= CAP:
            break
    LAST.update({"matched": matched, "edges": len(out), "entered": len(final), "espn_calls": sb.calls_used()})
    sb.save_athletes()
    for e in final:
        e.pop("_edge", None)
    return final
