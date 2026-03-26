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
            "live":  {"balance": 100.0,  "start": 100.0,  "peak": 100.0},
            "paper": {"balance": 1000.0, "start": 1000.0, "peak": 1000.0},
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


def main():
    outcomes   = read_outcomes()
    bankroll   = read_bankroll()
    changes    = read_model_changes()
    ai         = read_ai_suggestions()
    models     = read_models()
    stats      = calculate_stats(outcomes)

    # Live and paper P&L
    live_pnl  = round(bankroll.get("live",  {}).get("balance", 100)  - bankroll.get("live",  {}).get("start", 100),  2)
    paper_pnl = round(bankroll.get("paper", {}).get("balance", 1000) - bankroll.get("paper", {}).get("start", 1000), 2)

    recent = list(reversed(outcomes[-50:]))

    data = {
        "generated_at":   datetime.datetime.utcnow().isoformat() + "Z",
        "stats":          stats,
        "bankroll":       bankroll,
        "live_pnl":       live_pnl,
        "paper_pnl":      paper_pnl,
        "recent_alerts":  recent,
        "model_changes":  changes,
        "ai_suggestions": ai,
        "model_confidence": models.get("category_confidence", {}),
    }

    out = DOCS / "data.json"
    with open(out, "w") as f:
        json.dump(data, f, indent=2)

    print(
        f"✓ docs/data.json written — {len(recent)} alerts | "
        f"hit rate: {stats['hit_rate']}% | "
        f"live P&L: ${live_pnl:+.2f} | paper P&L: ${paper_pnl:+.2f}"
    )


if __name__ == "__main__":
    main()
