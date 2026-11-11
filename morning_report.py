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


def _account_snapshot(bankroll: dict) -> tuple:
    """(account dict, open positions list) from data/bankroll.json + data/positions.json."""
    import json
    live = (bankroll or {}).get("live", {})
    positions = []
    try:
        p = config.BASE_DIR / "data" / "positions.json"
        if p.exists():
            positions = json.loads(p.read_text())
    except Exception:
        positions = []
    pos_val = round(sum(float(x.get("current_value", 0) or 0) for x in positions), 2)
    cash = float(live.get("cash", live.get("balance", 0)) or 0)
    total = round(cash + pos_val, 2) if (cash or pos_val) else round(float(live.get("balance", 0) or 0), 2)
    initial = live.get("initial_balance")
    change = round(total - float(initial), 2) if initial else None
    return ({"cash": cash, "positions": pos_val, "total": total,
             "initial": float(initial) if initial else None, "change": change}, positions)


def run(api) -> None:
    log("=" * 60)
    log("Morning report starting")

    # Daily stale-position cleanup — moved here from every-scan to keep
    # the frequent 30-min scans from timing out on per-position sell calls.
    try:
        import auto_bettor
        stale = auto_bettor.cleanup_stale_positions(api)
        if stale:
            log(f"Morning stale-cleanup: {len(stale)} position(s) processed: {stale}")
    except Exception as exc:
        log(f"Morning stale-cleanup failed (non-fatal): {exc}", "WARN")

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

    # Audited numbers: each market counted once, net of fees (never raw-row sums)
    from outcomes import read_all as _read_all, audited_record
    all_outcomes = _read_all()
    audited = audited_record(all_outcomes)
    unit_total = audited["net_units"]

    # Real account: cash / positions / total vs initial_balance
    account, open_positions = _account_snapshot(bankroll)

    # Why-no-alerts line from scanner diagnostics
    import scoreboard
    diag_line = scoreboard.diag_line(scoreboard._load("scan_diag.json", {}))

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

    # Today's bets placed (last 24h)
    bets_today = []
    try:
        if config.BETS_PLACED_CSV.exists():
            _cutoff = datetime.datetime.utcnow() - datetime.timedelta(hours=24)
            with open(config.BETS_PLACED_CSV, newline="") as _f:
                for _row in __import__("csv").DictReader(_f):
                    _ts = _row.get("timestamp", "")
                    try:
                        _bet_ts = datetime.datetime.fromisoformat(
                            _ts.replace("Z", "+00:00")
                        ).replace(tzinfo=None)
                        if _bet_ts >= _cutoff:
                            bets_today.append(_row)
                    except Exception:
                        pass
    except Exception:
        pass

    # Compose and send
    report = {
        "hit_rate_summary":   analysis["hit_rate_summary"],
        "ai_summary":         analysis["ai_summary"],
        "stat_changes":       analysis["stat_changes"],
        "premarket_watch":    premarket,
        "bankroll":           bankroll,
        "unit_total":         unit_total,
        "audited":            audited,
        "account":            account,
        "open_positions":     open_positions,
        "diag_line":          diag_line,
        "resolved_overnight": resolved_overnight,
        "bets_today":         bets_today,
    }

    send_morning_report(report)
    try:
        scoreboard.post_daily()
    except Exception as exc:
        log(f"Scoreboard post failed (non-fatal): {exc}", "WARN")
    log("Morning report complete")
    log("=" * 60)


def run_weekly_review(api) -> None:
    """Sunday evening weekly wrap-up."""
    from discord_alerts import send_weekly_report
    from outcomes import read_all, hit_rate_summary

    log("Running weekly review")
    rows   = read_all()
    stats  = hit_rate_summary()
    aud    = stats.get("audited", {})

    # Filter to this week
    week_start = (datetime.datetime.utcnow() - datetime.timedelta(days=7)).isoformat()
    this_week  = [r for r in rows if r.get("timestamp", "") >= week_start]
    new_markets = len({r.get("ticker") for r in this_week})

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
        f"Hit rate is {stats.get('hit_rate','?')}% across {stats['rated']} resolved markets "
        f"({aud.get('net_units', 0):+.1f} units net of fees). "
        f"Best performing category: {best_cat}. "
        f"{'Models appear well-calibrated.' if (stats.get('hit_rate') or 0) >= 55 else 'Models need recalibration — reviewing confidence multipliers.'}"
    )

    report = {
        "stats": {
            "hit_rate":         stats.get("hit_rate"),
            "alerts_this_week": new_markets,
            "best_category":    best_cat,
            "worst_category":   worst_cat,
        },
        "bankroll_gains": {
            "live_pnl":  round(live_pnl,  2),
            "paper_pnl": round(paper_pnl, 2),
        },
        "summary": (
            f"Week ending {datetime.datetime.utcnow().strftime('%B %d, %Y')}. "
            f"{new_markets} distinct markets alerted this week ({len(this_week)} raw rows)."
        ),
        "audited_line": (f"{aud.get('markets_alerted', 0)} markets alerted, {aud.get('resolved_markets', 0)} resolved, "
                         f"{aud.get('wins', 0)} wins, {aud.get('net_units', 0):+.1f}u (per distinct market, net of fees)"),
        "paper_delta":  _paper_delta(),
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


def _paper_delta() -> str:
    """Week-over-week change per paper rule, from paper_summary.json (old_c/new_c are
    the net cents in the older vs newer half; prev snapshot kept in data/paper_week_prev.json)."""
    import json
    import scoreboard
    cur = scoreboard._load("paper_summary.json", {})
    prev_path = config.BASE_DIR / "data" / "paper_week_prev.json"
    try:
        prev = json.loads(prev_path.read_text()) if prev_path.exists() else {}
    except Exception:
        prev = {}
    if not cur:
        return "No paper data yet."
    lines = []
    for name, d in sorted(cur.items()):
        p = prev.get(name, {})
        de = (d.get("events") or 0) - (p.get("events") or 0)
        dn = None
        if d.get("net_c") is not None and p.get("net_c") is not None:
            dn = d["net_c"] - p["net_c"]
        lines.append(f"{name} [{d.get('status')}]: {d.get('events', 0)} events ({de:+d}), net "
                     f"{scoreboard._fmt(d.get('net_c'))}c" + (f" ({dn:+.1f}c vs last week)" if dn is not None else ""))
    try:
        prev_path.write_text(json.dumps({k: {"events": v.get("events"), "net_c": v.get("net_c")}
                                         for k, v in cur.items()}))
    except Exception:
        pass
    return "\n".join(lines)
