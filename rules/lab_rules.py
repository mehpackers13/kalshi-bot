"""Paper rule: trade whatever the strategy lab currently lists as 'passed'.

Reads data/lab_results.json['passed'] — executable-price candidates that cleared all four lab gates
(economics, adverse selection, Benjamini-Hochberg FDR, out-of-sample holdout). For each passed rule it
picks open markets whose series/category matches, whose executable YES-scale price (ask for a YES
entry, bid for a NO entry) lies in [lo, hi), 6-36h from close, volume >= 200. Entries are tagged
notes='lab:<rule_key>' so the paper engine's per-rule stats and kill switch can judge them.
Paper only. Nothing here promotes to real money.
"""
import json
from pathlib import Path

NAME = "lab_rules"
CAP = 40
PER_RULE = 10
RESULTS = Path(__file__).resolve().parent.parent / "data" / "lab_results.json"


def _load():
    try:
        return json.loads(RESULTS.read_text()).get("passed", [])
    except Exception:
        return []


def select(ctx):
    passed = _load()
    if not passed:
        return []
    markets = ctx.get("markets") or []
    out = []
    for r in passed:
        key = r.get("paper_rule") or f"lab:{r['kind']}:{r['name']}:{r['bucket']}:{r['side']}"
        side, lo, hi = r["side"], float(r["lo"]), float(r["hi"])
        h_min, h_max, min_vol = r.get("hours_min", 6), r.get("hours_max", 36), r.get("min_vol", 200)
        top = hi + (0.0001 if hi >= 1.0 else 0)
        cands = []
        for m in markets:
            if r["kind"] == "series":
                if m.get("series") != r["name"]:
                    continue
            elif r["name"] != "ALL" and m.get("category") != r["name"]:
                continue
            h = m.get("hours_to_close")
            if h is None or not (h_min <= h <= h_max) or (m.get("volume") or 0) < min_vol:
                continue
            bid, ask = m.get("yes_bid") or 0, m.get("yes_ask") or 0
            if not (1 <= bid and ask <= 99):
                continue
            px = (ask if side == "YES" else bid) / 100.0
            if not (lo <= px < top):
                continue
            cands.append((m.get("volume") or 0, m))
        cands.sort(key=lambda t: -t[0])
        seen_events = set()
        n = 0
        for _, m in cands:
            ev = m.get("event") or "-".join(m["ticker"].split("-")[:2])
            if ev in seen_events:       # one entry per event: strike ladders are one outcome
                continue
            seen_events.add(ev)
            out.append({"ticker": m["ticker"], "side": side, "category": m.get("category") or r["name"],
                        "event": ev, "series": m.get("series") or m["ticker"].split("-")[0],
                        "model_prob": None, "notes": key[:120]})
            n += 1
            if n >= PER_RULE:
                break
    return out[:CAP]
