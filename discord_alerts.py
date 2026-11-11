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
    """Send the daily morning briefing to #bot-health (audited numbers only)."""

    stats     = report.get("hit_rate_summary", {})
    aud       = report.get("audited") or stats.get("audited") or {}
    acct      = report.get("account") or {}
    ai        = report.get("ai_summary", "")
    premarket = report.get("premarket_watch", [])
    positions = report.get("open_positions", [])
    diag_line = report.get("diag_line", "")

    # Audited alert record (each market counted once, never raw-row sums)
    if aud:
        net = aud.get("net_units", 0.0)
        icon = "🟢" if net > 0 else "🔴" if net < 0 else "⚪"
        hr = aud.get("hit_rate")
        record = (
            f"{aud.get('markets_alerted', 0)} distinct markets alerted\n"
            f"{aud.get('resolved_markets', 0)} resolved, {aud.get('wins', 0)} wins"
            f" ({hr if hr is not None else '—'}% hit rate)\n"
            f"{icon} **{net:+.1f} units** (per distinct market, net of fees)"
        )
    else:
        record = "No audited record yet."

    # Real account
    if acct:
        chg = acct.get("change")
        acct_str = (f"Cash ${acct.get('cash', 0):.2f} | Positions ${acct.get('positions', 0):.2f}\n"
                    f"**Total ${acct.get('total', 0):.2f}**"
                    + (f" ({chg:+.2f} since ${acct.get('initial', 0):.2f} start)" if chg is not None else ""))
    else:
        acct_str = "Account not synced."

    # Category breakdown (distinct markets)
    cat_lines = []
    for cat, d in sorted((aud.get("by_category") or {}).items(), key=lambda x: -x[1]["markets"]):
        cat_lines.append(f"• **{cat}**: {d['markets']} markets, {d['wins']} wins, {d['net_units']:+.1f}u")
    cat_str = "\n".join(cat_lines) or "No resolved markets yet."

    premarket_str = ""
    if premarket:
        premarket_str = "\n".join(
            f"• [{m['ticker']}] {m['title']} — edge {m['edge_pct']:+.1f}%" for m in premarket[:5])

    overnight = report.get("resolved_overnight", [])
    if overnight:
        overnight_str = "\n".join(
            f"{'✅' if r.get('outcome') == '1' else '❌'} [{r.get('ticker','')}] {r.get('title','')[:60]}"
            for r in overnight[:5])
    else:
        overnight_str = "No markets resolved overnight."

    fields = [
        {"name": "💰 Your Kalshi account (real)", "value": acct_str[:1000], "inline": False},
        {"name": "📋 Alert record (audited)",     "value": record[:1000],   "inline": False},
    ]
    if diag_line:
        fields.append({"name": "🔎 Why no alerts", "value": diag_line[:1000], "inline": False})
    if positions:
        plines = [f"• `{p.get('ticker','')}` {p.get('direction','')} x{p.get('contracts','?')} "
                  f"— ${float(p.get('current_value', 0) or 0):.2f}" for p in positions[:5]]
        fields.append({"name": "📌 Open positions — held in your account (not placed by this bot's auto-bettor)",
                       "value": "\n".join(plines)[:1000], "inline": False})
    fields += [
        {"name": "🌙 Resolved Overnight",   "value": overnight_str[:1000], "inline": False},
        {"name": "Performance by Category", "value": cat_str[:1000],       "inline": False},
    ]
    if ai:
        fields.append({"name": "🧠 AI Brain — What I Learned", "value": ai[:1000], "inline": False})
    if premarket_str:
        fields.append({"name": "👀 Pre-Market Watch", "value": premarket_str[:1000], "inline": False})

    embed = {
        "title":       "☀️ Good Morning — Kalshi Bot Daily Briefing",
        "description": f"*{datetime.datetime.utcnow().strftime('%A, %B %d %Y')} UTC*",
        "color":       0x4A90D9,
        "fields":      fields,
        "footer":      {"text": "paper = pretend bets, no money moved • a week with zero alerts is a success"},
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
            {"name": "Audited record", "value": (report.get("audited_line") or "—")[:1000], "inline": False},
            {"name": "Paper rules (week-over-week)", "value": (report.get("paper_delta") or "No paper data yet.")[:1000], "inline": False},
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
