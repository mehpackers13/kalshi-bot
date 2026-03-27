"""
Webhook test + live scan diagnostic.
Sends a test ping to both Discord channels, then runs a full scan
and prints everything the bot found regardless of edge threshold.
"""

import datetime
import os
import sys

import config
from discord_alerts import _signals, _health
from kalshi_api import KalshiAPI, parse_market
from probability_models import estimate_true_probability
from edge_calculator import _gate_check
from logger import log


def test_webhooks():
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    ok_signals = _signals({
        "embeds": [{
            "title": "✅ kalshi-bot webhook test",
            "description": (
                "**#kalshi-signals** is connected and working.\n"
                f"Timestamp: `{ts}`\n\n"
                "Trade alerts will appear here whenever the bot finds an edge ≥8%."
            ),
            "color": 0x00C851,
            "footer": {"text": "kalshi-bot • webhook test"},
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        }]
    })

    ok_health = _health({
        "embeds": [{
            "title": "✅ kalshi-bot webhook test",
            "description": (
                "**#bot-health** is connected and working.\n"
                f"Timestamp: `{ts}`\n\n"
                "Morning reports, weekly reviews, and system alerts will appear here."
            ),
            "color": 0x388bfd,
            "footer": {"text": "kalshi-bot • webhook test"},
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        }]
    })

    return ok_signals, ok_health


def diagnostic_scan(api: KalshiAPI):
    """
    Full diagnostic: fetches all markets, runs all models, reports
    everything — including markets that passed filters but had no model,
    and the top candidates that came closest to the edge threshold.
    """
    log("=" * 60)
    log("DIAGNOSTIC SCAN — showing full detail")

    raw_markets = api.get_all_open_markets()
    log(f"Total open markets fetched: {len(raw_markets)}")

    parsed = [parse_market(m) for m in raw_markets]
    parsed = [m for m in parsed if m]
    log(f"Successfully parsed: {len(parsed)}")

    # Category breakdown
    cats = {}
    for m in parsed:
        c = m.get("category", "?")
        cats[c] = cats.get(c, 0) + 1
    log("Markets by category:")
    for cat, n in sorted(cats.items(), key=lambda x: -x[1]):
        marker = " ← modelable" if cat in config.MODELABLE_CATEGORIES else ""
        log(f"  {cat:<20} {n:>4}{marker}")

    # Gate failure breakdown — shows exactly why markets don't qualify
    gate_reasons = {}
    for m in parsed:
        reason = _gate_check(m)
        if reason:
            # Bucket by first two words of reason
            words  = reason.split()
            bucket = " ".join(words[:2]) if len(words) >= 2 else reason
            gate_reasons[bucket] = gate_reasons.get(bucket, 0) + 1
    if gate_reasons:
        log("Gate filter breakdown (of parsed markets):")
        for reason, n in sorted(gate_reasons.items(), key=lambda x: -x[1]):
            log(f"  {n:>4}x  {reason}")

    # Show a sample of the parsed markets so we can see what we're working with
    log("Sample of parsed markets (first 5):")
    for m in parsed[:5]:
        log(f"  [{m.get('category','')}] {m['ticker']} implied={m['implied_prob']:.1%} vol=${m['dollar_volume']:,.0f} h={m['hours_to_close']:.1f}h  title: {m['title'][:50]}")

    # Run models on every parsed market — category is no longer a gate.
    # estimate_true_probability() routes by title keywords, not category.
    results = []
    for m in parsed:
        gate_fail = _gate_check(m)
        true_prob = estimate_true_probability(m)

        if true_prob is not None:
            implied = m["implied_prob"]
            edge = (true_prob - implied) * 100
            results.append({
                "ticker":     m["ticker"],
                "title":      m["title"][:60],
                "category":   m["category"],
                "implied":    implied,
                "true_prob":  true_prob,
                "edge_pct":   edge,
                "gate_fail":  gate_fail,
                "vol":        m["dollar_volume"],
                "hours":      m["hours_to_close"],
            })

    # Sort by absolute edge
    results.sort(key=lambda x: -abs(x["edge_pct"]))

    qualifying = [r for r in results if r["gate_fail"] is None and abs(r["edge_pct"]) >= config.MIN_EDGE_PCT]
    near_miss  = [r for r in results if r["gate_fail"] is None and abs(r["edge_pct"]) >= 4 and abs(r["edge_pct"]) < config.MIN_EDGE_PCT]
    filtered   = [r for r in results if r["gate_fail"] is not None]

    log(f"\n{'='*60}")
    log(f"QUALIFYING EDGES (≥{config.MIN_EDGE_PCT}%): {len(qualifying)}")
    for r in qualifying[:20]:
        direction = "BUY YES" if r["edge_pct"] > 0 else "BUY NO"
        log(f"  [{r['category']}] {r['ticker']}")
        log(f"    {r['title']}")
        log(f"    implied={r['implied']:.1%}  model={r['true_prob']:.1%}  edge={r['edge_pct']:+.1f}%  vol=${r['vol']:,.0f}  {direction}")

    log(f"\nNEAR MISSES (4–{config.MIN_EDGE_PCT}% edge, passed filters): {len(near_miss)}")
    for r in near_miss[:10]:
        log(f"  [{r['category']}] {r['ticker']} edge={r['edge_pct']:+.1f}% implied={r['implied']:.1%} model={r['true_prob']:.1%}")

    log(f"\nFILTERED OUT (had a model but failed a gate): {len(filtered)}")
    for r in filtered[:10]:
        log(f"  [{r['category']}] {r['ticker']} edge={r['edge_pct']:+.1f}%  BLOCKED: {r['gate_fail']}")

    log(f"\nTotal modelable markets evaluated: {len(results)}")
    log("=" * 60)

    return qualifying


if __name__ == "__main__":
    log("=== KALSHI BOT TEST RUN ===")

    # 1. Test webhooks
    log("Testing Discord webhooks...")
    ok_sig, ok_hlth = test_webhooks()
    log(f"  #kalshi-signals : {'✅ OK' if ok_sig  else '❌ FAILED — check DISCORD_SIGNALS_WEBHOOK secret'}")
    log(f"  #bot-health     : {'✅ OK' if ok_hlth else '❌ FAILED — check DISCORD_HEALTH_WEBHOOK secret'}")

    if not ok_sig or not ok_hlth:
        log("Webhook test failed — check your secrets and re-run", "ERROR")
        sys.exit(1)

    # 2. Connect to Kalshi
    api = KalshiAPI()
    logged_in = api.login()
    if not logged_in:
        log("Kalshi API key auth failed — check KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY secrets", "ERROR")
        log("Markets are still fetched publicly — running diagnostic scan anyway")
        # Don't exit — public market scanning works without auth

    # 3. Full diagnostic scan
    qualifying = diagnostic_scan(api)

    # 4. Send summary to Discord
    if qualifying:
        lines = []
        for r in qualifying[:10]:
            d = "↑ YES" if r["edge_pct"] > 0 else "↓ NO"
            lines.append(
                f"**{r['ticker']}** [{r['category']}] "
                f"edge **{r['edge_pct']:+.1f}%** {d} "
                f"| implied {r['implied']:.1%} → model {r['true_prob']:.1%}"
            )
        summary = "\n".join(lines)
        _health({
            "embeds": [{
                "title": f"🔍 Diagnostic Scan Complete — {len(qualifying)} edges found",
                "description": summary,
                "color": 0x00C851,
                "footer": {"text": "kalshi-bot diagnostic"},
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            }]
        })
    else:
        _health({
            "embeds": [{
                "title": "🔍 Diagnostic Scan Complete — no edges today",
                "description": (
                    "Scanned all Kalshi markets. No qualifying edges found right now.\n"
                    "This is correct bot behaviour — it only alerts on genuine opportunities."
                ),
                "color": 0x888888,
                "footer": {"text": "kalshi-bot diagnostic"},
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            }]
        })

    log("Test run complete")
