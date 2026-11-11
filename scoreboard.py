"""
SCOREBOARD
==========
Daily plain-language scoreboard for the paper-trading rules.
Reads (all optional, absence tolerated):
  data/paper_summary.json   paper_lab rule stats
  data/crypto_summary.json  crypto_lab stats
  data/lab_results.json     strategy_lab candidates (in-sample only)
  data/paper_events.log     status-change events (kill / candidate)
  data/scan_diag.json       scanner counters
Posts to the health webhook; kill/candidate events go to the signals webhook.
Paper = pretend bets. No money moves.
"""

import json
import datetime
from pathlib import Path

DATA = Path(__file__).parent / "data"
CURSOR = DATA / "paper_events_posted.json"
FIELD_MAX = 1000


def _load(name, default):
    try:
        return json.loads((DATA / name).read_text())
    except Exception:
        return default


def _fmt(v, nd=1, sign=True):
    if v is None or v == "":
        return "-"
    try:
        return f"{float(v):+.{nd}f}" if sign else f"{float(v):.{nd}f}"
    except Exception:
        return str(v)


def paper_table(summary: dict) -> str:
    if not summary:
        return "No paper summary yet."
    lines = [f"{'rule':<20}{'status':<10}{'ev':>4}{'net¢':>6}  {'95% CI':<14}{'CLV¢':>6}{'open':>5}"]
    order = {"candidate": 0, "active": 1, "killed": 2}
    for name, d in sorted(summary.items(), key=lambda kv: (order.get(kv[1].get("status"), 3), kv[0])):
        ci = f"[{_fmt(d.get('lo_c'))},{_fmt(d.get('hi_c'))}]" if d.get("lo_c") is not None else "-"
        ev = f"{d.get('settled', 0)}/{d.get('events', 0)}"
        lines.append(
            f"{name[:22]:<23}{str(d.get('status', '?'))[:9]:<10}{ev:>4}{_fmt(d.get('net_c')):>6}  "
            f"{ci:<14}{_fmt(d.get('clv_c')):>6}{d.get('open', 0):>5}"
        )
    lines.append("ev = settled/events (ladders count once)")
    return "\n".join(lines)


def crypto_lines(crypto: dict) -> str:
    if not crypto:
        return "No crypto paper results yet."
    strat = crypto.get("strategies") if isinstance(crypto.get("strategies"), dict) else None
    if strat is None:
        strat = {k: v for k, v in crypto.items() if isinstance(v, dict)}
    out = []
    for name, v in list(strat.items())[:8]:
        n = v.get("n_closed", v.get("settled", 0))
        mean = v.get("mean_pnl_pct")
        lo, hi = v.get("ci95_lo"), v.get("ci95_hi")
        ci = f" CI [{_fmt(lo)},{_fmt(hi)}]%" if lo is not None and hi is not None else ""
        out.append(f"{name[:22]:<22} {n} closed, {v.get('open', 0)} open"
                   + (f", mean {_fmt(mean)}%{ci}" if mean is not None else ""))
    out.append("pretend only; nothing proven under 30 closed")
    return "\n".join(out)


def lab_lines(lab: dict, n: int = 5) -> str:
    lab = lab or {}
    passed = lab.get("passed") or []
    legacy = lab.get("legacy_vwap_passes")
    legacy_n = len(legacy) if isinstance(legacy, list) else legacy
    if not passed:
        extra = f" ({legacy_n} older VWAP-priced passes are not trusted)" if legacy_n else ""
        return f"No lab candidates at executable prices{extra}."
    rows = sorted(passed, key=lambda r: -(r.get("lo_c") or 0))[:n]
    out = [f"{len(passed)} passed the lab (in-sample only, not proof):"]
    for r in rows:
        out.append(f"{r.get('name')} {r.get('bucket', '')} {r.get('side', '')}: "
                   f"{r.get('events')} ev, net {_fmt(r.get('net_c'))}c, "
                   f"CI [{_fmt(r.get('lo_c'))},{_fmt(r.get('hi_c'))}]")
    return "\n".join(out)


def diag_line(diag: dict) -> str:
    if not diag:
        return "No scan diagnostics yet."
    gf = diag.get("gate_fail") or {}
    passed = diag.get("gate_pass")
    if passed is None:
        passed = diag.get("passed_gates")
    if passed is None:
        passed = diag.get("passed_liquidity_time")
    p = f"{passed}" if passed is not None else "?"
    return (f"fetched {diag.get('fetched', '?')} markets, {diag.get('closing_within_60d', '?')} close <=60d, "
            f"{p} passed liquidity/time gates, {diag.get('modelable', '?')} modelable, "
            f"{diag.get('edges', '?')} edges"
            + (f" (gate fails: {gf})" if gf and passed is None else ""))


def _chunks(text: str, limit: int = FIELD_MAX, wrap: bool = False) -> list:
    """Split text on line boundaries into pieces <= limit (code fence overhead included)."""
    budget = limit - (8 if wrap else 0)
    parts, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > budget and cur:
            parts.append(cur)
            cur = ""
        cur += line[:budget] + "\n"
    if cur.strip():
        parts.append(cur)
    return [f"```\n{p.rstrip()}\n```" if wrap else p.rstrip() for p in parts]


def _fields(name: str, text: str, wrap: bool = False) -> list:
    return [{"name": name if i == 0 else name + " (cont.)", "value": c, "inline": False}
            for i, c in enumerate(_chunks(text, wrap=wrap))]


def summarize_text() -> str:
    parts = ["PAPER RULES", paper_table(_load("paper_summary.json", {})),
             "", "CRYPTO PAPER", crypto_lines(_load("crypto_summary.json", {})),
             "", "LAB CANDIDATES", lab_lines(_load("lab_results.json", {})),
             "", "WHY NO ALERTS", diag_line(_load("scan_diag.json", {}))]
    return "\n".join(parts)


def build_scoreboard() -> dict:
    fields = []
    fields += _fields("Paper rules", paper_table(_load("paper_summary.json", {})), wrap=True)
    fields += _fields("Crypto paper", crypto_lines(_load("crypto_summary.json", {})), wrap=True)
    fields += _fields("Lab candidates (in-sample only)", lab_lines(_load("lab_results.json", {})), wrap=True)
    return {
        "title": "Paper Scoreboard",
        "description": ("Pretend bets only. 'candidate' = passed the statistical gate, awaiting Mike's decision. "
                        "'killed' = switched off after losing."),
        "color": 0x2E86C1,
        "fields": fields[:20],
        "footer": {"text": "paper = pretend bets, no money moved"},
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }


def _new_events() -> tuple:
    path = DATA / "paper_events.log"
    if not path.exists():
        return [], 0
    lines = [l for l in path.read_text().splitlines() if l.strip()]
    cur = _load("paper_events_posted.json", {}).get("lines_posted", 0)
    if cur > len(lines):   # log was truncated/rotated
        cur = 0
    return lines[cur:], len(lines)


def post_events() -> int:
    """Post new kill/candidate events to the signals webhook. Returns count posted."""
    import discord_alerts
    new, total = _new_events()
    if not new:
        return 0
    desc = "\n".join(l[:300] for l in new[:15])
    ok_embed = {
        "title": "Paper rule status change",
        "description": f"```\n{desc[:3800]}\n```",
        "color": 0xF39C12,
        "footer": {"text": "paper = pretend bets, no money moved"},
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }
    sent = discord_alerts._signals({"embeds": [ok_embed]})
    # Advance the cursor only when truly delivered, or when no webhook exists
    # (local test mode prints, so don't re-print forever either way in CI).
    import config
    if sent or not config.DISCORD_SIGNALS_WEBHOOK:
        if sent:
            try:
                CURSOR.write_text(json.dumps({"lines_posted": total,
                                              "at": datetime.datetime.utcnow().isoformat() + "Z"}))
            except Exception:
                pass
    return len(new)


def post_daily() -> bool:
    import discord_alerts
    from logger import log
    try:
        ok = discord_alerts._health({"embeds": [build_scoreboard()]})
    except Exception as exc:
        log(f"[scoreboard] post failed: {exc}", "WARN")
        ok = False
    try:
        post_events()
    except Exception as exc:
        log(f"[scoreboard] events post failed: {exc}", "WARN")
    return ok


if __name__ == "__main__":
    print(summarize_text())
