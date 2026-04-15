"""
generate_data.py
================
Converts outcomes.csv, bankroll.json, model_changes.log, and AI suggestions
into docs/data.json for the GitHub Pages dashboard.
Run automatically by GitHub Actions after every scan.
Run manually: python generate_data.py
"""

import csv
import json
import datetime
from pathlib import Path
from collections import defaultdict

STARTING_BANKROLL = 10.0   # must match config.py

BASE = Path(__file__).parent
DOCS = BASE / "docs"
DATA = BASE / "data"
DOCS.mkdir(exist_ok=True)


def read_outcomes():
    path = BASE / "outcomes.csv"
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return [r for r in csv.DictReader(f) if r.get("timestamp")]


def read_bankroll():
    path = DATA / "bankroll.json"
    if not path.exists():
        return {
            "live":  {"balance": 0.0,    "peak": 0.0},
            "paper": {"balance": 1000.0, "peak": 1000.0},
        }
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def read_model_changes():
    path = BASE / "model_changes.log"
    if not path.exists():
        return []
    return [l for l in path.read_text().splitlines() if l.strip()][-30:]


def read_ai_suggestions():
    path = DATA / "ai_suggestions.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def read_models():
    path = DATA / "models.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def calculate_stats(outcomes):
    if not outcomes:
        return {
            "total_alerts": 0, "rated": 0, "hit_rate": None,
            "by_category": {}, "by_edge_bucket": {},
            "live_pnl": 0.0, "paper_pnl": 0.0,
        }

    rated = [r for r in outcomes if r.get("outcome") in ("0", "1")]
    hits  = [r for r in rated if r.get("outcome") == "1"]
    hr    = round(len(hits) / len(rated) * 100, 1) if rated else None

    by_cat = defaultdict(lambda: {"total": 0, "rated": 0, "hits": 0})
    for r in outcomes:
        c = r.get("category", "Unknown")
        by_cat[c]["total"] += 1
        if r.get("outcome") in ("0", "1"):
            by_cat[c]["rated"] += 1
            if r["outcome"] == "1":
                by_cat[c]["hits"] += 1

    def _bucket(r):
        try:
            e = abs(float(r.get("edge_pct", 0) or 0))
        except Exception:
            e = 0
        if e >= 25:  return "strong (25%+)"
        if e >= 15:  return "medium (15-25%)"
        return "small (8-15%)"

    by_bucket = defaultdict(lambda: {"total": 0, "rated": 0, "hits": 0})
    for r in outcomes:
        b = _bucket(r)
        by_bucket[b]["total"] += 1
        if r.get("outcome") in ("0", "1"):
            by_bucket[b]["rated"] += 1
            if r["outcome"] == "1":
                by_bucket[b]["hits"] += 1

    def _finalize(d):
        return {
            cat: {
                "total":    v["total"],
                "rated":    v["rated"],
                "hits":     v["hits"],
                "hit_rate": round(v["hits"] / v["rated"] * 100, 1) if v["rated"] > 0 else None,
            }
            for cat, v in d.items()
        }

    return {
        "total_alerts":  len(outcomes),
        "rated":         len(rated),
        "hit_rate":      hr,
        "by_category":   _finalize(by_cat),
        "by_edge_bucket": _finalize(by_bucket),
    }


def read_bets_placed():
    path = BASE / "bets_placed.csv"
    if not path.exists():
        return []
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    return list(reversed(rows[-50:]))   # last 50, newest first


def read_open_positions():
    """Load current open positions snapshot written by scanner during scan."""
    path = DATA / "positions.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except Exception:
        return []


def calc_unit_total(outcomes):
    """Sum units from resolved outcomes. Uses units_pl if present, otherwise calculates on-the-fly."""
    unit_size = STARTING_BANKROLL * 0.01  # $0.10 per unit
    total = 0.0
    for r in outcomes:
        if r.get("outcome") not in ("0", "1"):
            continue
        try:
            stored = r.get("units_pl", "")
            if stored not in (None, ""):
                total += float(stored)
            else:
                # Fall back: calculate from dollars and implied_prob
                dollars  = float(r.get("suggested_live_dollars") or 0)
                imp_prob = float(r.get("implied_prob") or 0)
                if dollars <= 0 or imp_prob <= 0:
                    continue
                if r["outcome"] == "1":
                    payout = dollars * (1.0 / imp_prob - 1.0)
                    total += payout / unit_size
                else:
                    total -= dollars / unit_size
        except Exception:
            pass
    return round(total, 3)


def read_today_outcomes(outcomes):
    """Return outcomes logged in the last 24 hours."""
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
    today = []
    for r in outcomes:
        ts_str = r.get("timestamp", "")
        try:
            ts = datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if ts.replace(tzinfo=None) >= cutoff:
                today.append(r)
        except Exception:
            pass
    return list(reversed(today))


def main():
    outcomes      = read_outcomes()
    bankroll      = read_bankroll()
    changes       = read_model_changes()
    ai            = read_ai_suggestions()
    models        = read_models()
    stats         = calculate_stats(outcomes)
    bets_placed   = read_bets_placed()
    open_positions = read_open_positions()
    unit_total    = calc_unit_total(outcomes)
    today_outcomes = read_today_outcomes(outcomes)
    generated     = datetime.datetime.utcnow().isoformat() + "Z"

    # Live balance breakdown: cash (spendable) + open position market value = total
    live_info  = bankroll.get("live", {})
    live_total = live_info.get("balance", 0)          # total = cash + positions (from drawdown tracker)
    cash_bal   = live_info.get("cash", live_total)    # cash-only (stored since bankroll.py update)
    live_peak  = live_info.get("peak", 0)
    # Position value: sum of current_value from fresh positions.json snapshot
    position_value = round(sum(float(p.get("current_value", 0) or 0) for p in open_positions), 2)
    # Account value: prefer cash + positions (positions.json is freshest), fall back to stored total
    if cash_bal > 0 or position_value > 0:
        account_value = round(cash_bal + position_value, 2)
    else:
        account_value = round(live_total, 2)
    live_pnl  = round(account_value - STARTING_BANKROLL, 2)
    paper_pnl = round(bankroll.get("paper", {}).get("balance", 1000) - STARTING_BANKROLL * 100, 2)

    recent = list(reversed(outcomes[-50:]))

    data = {
        "generated_at":    generated,
        "last_scan_ts":    generated,
        "stats":           stats,
        "bankroll":        bankroll,
        "cash_bal":        cash_bal,
        "position_value":  position_value,
        "account_value":   account_value,
        "live_pnl":        live_pnl,
        "paper_pnl":       paper_pnl,
        "unit_total":      unit_total,
        "today_outcomes":  today_outcomes,
        "recent_alerts":   recent,
        "model_changes":   changes,
        "ai_suggestions":  ai,
        "model_confidence": models.get("category_confidence", {}),
        "bets_placed":     bets_placed,
        "open_positions":  open_positions,
        "dry_run":         False,
    }

    out = DOCS / "data.json"
    with open(out, "w") as f:
        json.dump(data, f, indent=2)

    u_sign = "+" if unit_total >= 0 else ""
    print(
        f"✓ docs/data.json written — {len(recent)} alerts | "
        f"hit rate: {stats['hit_rate']}% | "
        f"cash: ${cash_bal:.2f} | positions: ${position_value:.2f} | total: ${account_value:.2f} (P&L {live_pnl:+.2f}) | units: {u_sign}{unit_total}u"
    )


if __name__ == "__main__":
    main()
