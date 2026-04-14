"""
MORNING REPORT
==============
Runs at 8am ET every weekday.
Compiles performance stats, AI insights, and pre-market watch.
Sends briefing to Discord #bot-health channel.
"""

import datetime

import config
from self_improve import run_morning_analysis
from scanner import premarket_watch
from bankroll import load_bankroll
from discord_alerts import send_morning_report
from logger import log


def run(api) -> None:
    log("=" * 60)
    log("Morning report starting")

    # Self-improvement analysis (stats + model adjustments + AI)
    analysis = run_morning_analysis()

    # Pre-market watch — what markets are worth watching today
    log("Scanning for pre-market opportunities...")
    premarket = premarket_watch(api, max_markets=8)
    if premarket:
        log(f"Pre-market watch: {len(premarket)} markets flagged")
    else:
        log("Pre-market watch: nothing qualifying found (fine)")

    # Bankroll
    bankroll = load_bankroll()

    # Calculate unit total
    from outcomes import read_all as _read_all
    all_outcomes = _read_all()
    unit_size = config.STARTING_BANKROLL * 0.01
    unit_total = sum(
        float(r.get("units_pl") or 0)
        for r in all_outcomes if r.get("outcome") in ("0", "1")
    )
    unit_total = round(unit_total, 3)

    # Count what resolved overnight (last 8h)
    from datetime import timezone as _tz
    cutoff_8h = datetime.datetime.utcnow() - datetime.timedelta(hours=8)
    resolved_overnight = [
        r for r in all_outcomes
        if r.get("resolved_at") and r.get("outcome") in ("0", "1")
        and (lambda ts: datetime.datetime.fromisoformat(
            ts.replace("Z", "+00:00")).replace(tzinfo=None) >= cutoff_8h
        )(r["resolved_at"])
    ]

    # Compose and send
    report = {
        "hit_rate_summary":   analysis["hit_rate_summary"],
        "ai_summary":         analysis["ai_summary"],
        "stat_changes":       analysis["stat_changes"],
        "premarket_watch":    premarket,
        "bankroll":           bankroll,
        "unit_total":         unit_total,
        "resolved_overnight": resolved_overnight,
    }

    send_morning_report(report)
    log("Morning report complete")
    log("=" * 60)


def run_weekly_review(api) -> None:
    """Sunday evening weekly wrap-up."""
    from discord_alerts import send_weekly_report
    from outcomes import read_all, hit_rate_summary

    log("Running weekly review")
    rows   = read_all()
    stats  = hit_rate_summary()

    # Filter to this week
    week_start = (datetime.datetime.utcnow() - datetime.timedelta(days=7)).isoformat()
    this_week  = [r for r in rows if r.get("timestamp", "") >= week_start]

    # Best/worst category
    by_cat = stats.get("by_category", {})
    rated_cats = {c: d for c, d in by_cat.items() if d.get("hit_rate") is not None}
    best_cat  = max(rated_cats, key=lambda c: rated_cats[c]["hit_rate"]) if rated_cats else "—"
    worst_cat = min(rated_cats, key=lambda c: rated_cats[c]["hit_rate"]) if rated_cats else "—"

    br = load_bankroll()
    live_pnl  = br["live"]["balance"]  - br["live"]["peak"]   # negative = drawdown from peak
    paper_pnl = br["paper"]["balance"] - br["paper"]["peak"]

    learned = (
        "Still accumulating data." if len(rows) < 20 else
        f"Hit rate is {stats.get('hit_rate','?')}% across {stats['rated']} rated alerts. "
        f"Best performing category: {best_cat}. "
        f"{'Models appear well-calibrated.' if (stats.get('hit_rate') or 0) >= 55 else 'Models need recalibration — reviewing confidence multipliers.'}"
    )

    report = {
        "stats": {
            "hit_rate":         stats.get("hit_rate"),
            "alerts_this_week": len(this_week),
            "best_category":    best_cat,
            "worst_category":   worst_cat,
        },
        "bankroll_gains": {
            "live_pnl":  round(live_pnl,  2),
            "paper_pnl": round(paper_pnl, 2),
        },
        "summary": (
            f"Week ending {datetime.datetime.utcnow().strftime('%B %d, %Y')}. "
            f"{len(this_week)} alerts fired this week."
        ),
        "learned":     learned,
        "next_focus":  (
            f"Continue monitoring {best_cat} markets. "
            "Keep edge threshold at 8%+ and let the models compound."
            if best_cat != "—" else
            "Focus on building outcome data — rate every alert as it resolves."
        ),
    }

    send_weekly_report(report)
    log("Weekly review sent")
