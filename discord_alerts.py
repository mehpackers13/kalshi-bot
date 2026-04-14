"""
DISCORD ALERTS
==============
Formats and sends alerts to two Discord channels:
  • #kalshi-signals  — trade opportunities (signals webhook)
  • #bot-health      — system updates, morning report, errors
"""

import json
import datetime
import requests

import config
from logger import log


# ── Core sender ─────────────────────────────────────────────────────────────────

def _send(webhook_url: str, payload: dict) -> bool:
    if not webhook_url:
        log("[Discord] No webhook URL — printing alert instead")
        print(json.dumps(payload, indent=2))
        return False
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code in (200, 204):
            return True
        log(f"[Discord] HTTP {resp.status_code}: {resp.text[:200]}", "WARN")
    except Exception as exc:
        log(f"[Discord] Send error: {exc}", "WARN")
    return False


def _signals(payload: dict) -> bool:
    return _send(config.DISCORD_SIGNALS_WEBHOOK, payload)

def _health(payload: dict) -> bool:
    return _send(config.DISCORD_HEALTH_WEBHOOK, payload)


# ── Trade signal alert ───────────────────────────────────────────────────────────

def send_trade_alert(edge, sizing: dict) -> None:
    """Send a full trade opportunity embed to #kalshi-signals."""

    edge_pct = edge.edge_pct
    direction = edge.direction

    # Color: green for strong edge, yellow for moderate, orange for small
    if abs(edge_pct) >= 25:
        color = 0x00C851   # green
    elif abs(edge_pct) >= 15:
        color = 0xFFBB33   # amber
    else:
        color = 0xFF8800   # orange

    # Buy direction label
    if direction == "YES":
        action_label = f"BUY YES @ {edge.yes_ask}¢"
        contract_prob = f"{edge.implied_prob:.1%} → our model: {edge.true_prob:.1%}"
    else:
        no_price = 100 - edge.yes_bid
        action_label = f"BUY NO @ {no_price}¢"
        contract_prob = f"NO implied: {(1-edge.implied_prob):.1%} → our model: {(1-edge.true_prob):.1%}"

    # Hours to close
    hrs = edge.hours_to_close
    if hrs >= 48:
        time_label = f"{hrs/24:.0f} days"
    elif hrs >= 1:
        time_label = f"{hrs:.1f} hours"
    else:
        time_label = f"{hrs*60:.0f} minutes"

    fields = [
        {"name": "Market",          "value": f"```{edge.title}```",              "inline": False},
        {"name": "Category",        "value": edge.category,                      "inline": True},
        {"name": "Ticker",          "value": f"`{edge.ticker}`",                 "inline": True},
        {"name": "Time to Close",   "value": time_label,                         "inline": True},
        {"name": "Action",          "value": f"**{action_label}**",              "inline": True},
        {"name": "Edge",            "value": f"**{abs(edge_pct):.1f}%**",        "inline": True},
        {"name": "Confidence",      "value": f"{edge.confidence}/100",           "inline": True},
        {"name": "Probability",     "value": contract_prob,                      "inline": False},
        {"name": "Volume",          "value": f"${edge.dollar_volume:,.0f}",      "inline": True},
        {
            "name": "Suggested Bet — LIVE ($100 bankroll)",
            "value": (
                f"${sizing['live_dollars']:.2f} "
                f"({sizing['live_contracts']} contracts) "
                f"— {sizing['capped_pct']:.1f}% of bankroll"
            ),
            "inline": False,
        },
        {
            "name": "Suggested Bet — PAPER ($1,000 bankroll)",
            "value": (
                f"${sizing['paper_dollars']:.2f} "
                f"({sizing['paper_contracts']} contracts)"
            ),
            "inline": False,
        },
        {"name": "Reasoning",       "value": edge.reasoning,                     "inline": False},
    ]

    embed = {
        "title":       f"🎯 Kalshi Edge Found — {edge.category}",
        "description": f"Edge: **{abs(edge_pct):.1f}%** | Direction: **{direction}**",
        "color":       color,
        "fields":      fields,
        "footer":      {"text": "kalshi-bot • disciplined & selective"},
        "timestamp":   datetime.datetime.utcnow().isoformat() + "Z",
    }

    _signals({"embeds": [embed]})
    log(f"[Discord] Trade alert sent: {edge.ticker}")


# ── Drawdown stop alert ──────────────────────────────────────────────────────────

def send_drawdown_stop(live_balance: float, peak_balance: float) -> None:
    drop_pct = (peak_balance - live_balance) / peak_balance * 100 if peak_balance > 0 else 0
    embed = {
        "title":       "🛑 DRAWDOWN STOP TRIGGERED",
        "description": (
            f"Live bankroll has dropped **{drop_pct:.1f}%** below peak balance.\n"
            f"**Current: ${live_balance:.2f}** | Peak ever: ${peak_balance:.2f}\n\n"
            "The bot will **not** suggest further live bets until you manually reset.\n"
            "Review your outcomes and assess what went wrong before resuming."
        ),
        "color":   0xFF4444,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }
    _health({"embeds": [embed]})
    _signals({"embeds": [embed]})


# ── Morning report ───────────────────────────────────────────────────────────────

def send_morning_report(report: dict) -> None:
    """Send the daily morning briefing to #bot-health."""

    stats   = report.get("hit_rate_summary", {})
    br      = report.get("bankroll", {})
    ai      = report.get("ai_summary", "")
    premarket = report.get("premarket_watch", [])

    hit_str = f"{stats.get('hit_rate', '—')}%" if stats.get("hit_rate") else "Not enough data yet"
    live_bal  = br.get("live",  {}).get("balance", 0.0)
    paper_bal = br.get("paper", {}).get("balance", config.PAPER_BANKROLL_START)

    # Category breakdown
    by_cat = stats.get("by_category", {})
    cat_lines = []
    for cat, d in sorted(by_cat.items(), key=lambda x: -(x[1].get("hit_rate") or 0)):
        hr = d.get("hit_rate")
        cat_lines.append(f"• **{cat}**: {d['count']} alerts, {hr}% hit rate" if hr else
                         f"• **{cat}**: {d['count']} alerts, pending")
    cat_str = "\n".join(cat_lines) if cat_lines else "No rated alerts yet."

    # Premarket watch
    premarket_str = ""
    if premarket:
        lines = [f"• [{m['ticker']}] {m['title']} — edge {m['edge_pct']:+.1f}%" for m in premarket[:5]]
        premarket_str = "\n".join(lines)

    # Unit P&L
    unit_total = report.get("unit_total", None)
    if unit_total is not None:
        u_sign = "+" if unit_total >= 0 else ""
        unit_str = f"{u_sign}{unit_total:.2f}u"
        unit_color = "🟢" if unit_total > 0 else "🔴" if unit_total < 0 else "⚪"
    else:
        unit_str = "—"
        unit_color = "⚪"

    # Resolved overnight
    overnight = report.get("resolved_overnight", [])
    if overnight:
        o_lines = []
        for r in overnight[:5]:
            outcome_icon = "✅" if r.get("outcome") == "1" else "❌"
            o_lines.append(f"{outcome_icon} [{r.get('ticker','')}] {r.get('title','')[:60]}")
        overnight_str = "\n".join(o_lines)
    else:
        overnight_str = "No markets resolved overnight."

    fields = [
        {"name": f"{unit_color} Kalshi Units",  "value": unit_str,                            "inline": True},
        {"name": "Overall Hit Rate",            "value": hit_str,                             "inline": True},
        {"name": "Live Bankroll",               "value": f"${live_bal:.2f}",                  "inline": True},
        {"name": "Total Alerts",                "value": str(stats.get("total_alerts", 0)),   "inline": True},
        {"name": "Rated",                       "value": str(stats.get("rated", 0)),          "inline": True},
        {"name": "Paper Bankroll",              "value": f"${paper_bal:.2f}",                 "inline": True},
        {"name": "🌙 Resolved Overnight",       "value": overnight_str,                       "inline": False},
        {"name": "Performance by Category",     "value": cat_str or "—",                      "inline": False},
    ]

    if ai:
        fields.append({"name": "🧠 AI Brain — What I Learned", "value": ai[:1000], "inline": False})

    if premarket_str:
        fields.append({"name": "👀 Pre-Market Watch",          "value": premarket_str, "inline": False})

    embed = {
        "title":       "☀️ Good Morning — Kalshi Bot Daily Briefing",
        "description": f"*{datetime.datetime.utcnow().strftime('%A, %B %d %Y')} UTC*",
        "color":       0x4A90D9,
        "fields":      fields,
        "footer":      {"text": "kalshi-bot • a week with zero alerts is a success"},
        "timestamp":   datetime.datetime.utcnow().isoformat() + "Z",
    }

    _health({"embeds": [embed]})
    log("[Discord] Morning report sent")


# ── Weekly report ────────────────────────────────────────────────────────────────

def send_weekly_report(report: dict) -> None:
    """Sunday evening full-week review to #bot-health."""

    stats = report.get("stats", {})
    gains = report.get("bankroll_gains", {})

    embed = {
        "title":       "📅 Weekly Review — Kalshi Bot",
        "description": report.get("summary", "Weekly performance summary."),
        "color":       0x9B59B6,
        "fields": [
            {"name": "Week Hit Rate",   "value": f"{stats.get('hit_rate','—')}%", "inline": True},
            {"name": "Alerts Fired",    "value": str(stats.get("alerts_this_week", 0)), "inline": True},
            {"name": "Live P&L",        "value": f"${gains.get('live_pnl', 0):+.2f}", "inline": True},
            {"name": "Paper P&L",       "value": f"${gains.get('paper_pnl', 0):+.2f}", "inline": True},
            {"name": "Best Category",   "value": stats.get("best_category", "—"),  "inline": True},
            {"name": "Worst Category",  "value": stats.get("worst_category", "—"), "inline": True},
            {"name": "What I Learned",  "value": report.get("learned", "More data needed."), "inline": False},
            {"name": "Next Week Focus", "value": report.get("next_focus", "Continue current approach."), "inline": False},
        ],
        "footer":    {"text": "kalshi-bot weekly review"},
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }
    _health({"embeds": [embed]})
    log("[Discord] Weekly report sent")


# ── Health ping ──────────────────────────────────────────────────────────────────

def send_health_ping(message: str, level: str = "INFO") -> None:
    icons = {"INFO": "ℹ️", "WARN": "⚠️", "ERROR": "🔴", "OK": "✅"}
    icon  = icons.get(level, "ℹ️")
    color_map = {"INFO": 0x888888, "WARN": 0xFFBB33, "ERROR": 0xFF4444, "OK": 0x00C851}
    _health({
        "embeds": [{
            "title":     f"{icon} Kalshi Bot — {level}",
            "description": message,
            "color":     color_map.get(level, 0x888888),
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        }]
    })
