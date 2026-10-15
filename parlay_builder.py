"""
PARLAY BUILDER
==============
Decides when to combine two or more edges into a Kalshi multi-leg combo
bet instead of taking them as singles. Lives behind config.PARLAY_LIVE —
default OFF — so the code ships but doesn't execute until you flip the
flag after validating against live Kalshi collection_tickers.

Pairing rules (conservative on purpose — bad legs multiply, not add):
  1. ALL legs must independently clear MIN_LEG_CONFIDENCE
  2. ALL legs must independently clear MIN_LEG_EDGE_PCT
  3. Legs are grouped by (sport, same calendar day) first
  4. Max MAX_LEGS per parlay (3 default)
  5. Combined implied win-prob of all legs multiplied must still beat
     the market price for the combo contract by MIN_PARLAY_EDGE_PCT
  6. Parlay sized at PARLAY_PCT_OF_BANKROLL (default 1.5%) — half of
     single-bet cap because variance is multiplicative

To go live:
  config.PARLAY_LIVE = True
  (optionally lower PARLAY_PCT_OF_BANKROLL if you want to be gentler)
"""
from __future__ import annotations

import datetime
from typing import Optional

import config
from logger import log

# ── Tunables (safe defaults) ─────────────────────────────────────────────────
MIN_LEG_CONFIDENCE   = 70
MIN_LEG_EDGE_PCT     = 10.0
MAX_LEGS             = 3
MIN_PARLAY_EDGE_PCT  = 15.0        # combo edge must beat this (singles only need 8%)
PARLAY_PCT_OF_BANKROLL = 0.015     # 1.5% max per parlay (half single-bet cap)


# ── Compatibility: find legs that CAN be parlayed on Kalshi ─────────────────
def _group_candidates(edges: list) -> list:
    """
    Group same-day same-sport edges into candidate parlay bundles.
    Each edge is expected to carry at least `.ticker`, `.direction`,
    `.confidence`, `.edge_pct`, `.true_prob` and (optionally) `.league`.
    """
    groups: dict = {}
    for e in edges:
        conf  = getattr(e, "confidence", 0) or 0
        edge  = getattr(e, "edge_pct",   0) or 0
        if conf < MIN_LEG_CONFIDENCE or edge < MIN_LEG_EDGE_PCT:
            continue
        league = getattr(e, "league", None) or _infer_league(getattr(e, "ticker", ""))
        if not league:
            continue
        # Group by (league, YYYY-MM-DD-ish component of ticker) — same slate.
        slate = _slate_key(getattr(e, "ticker", ""))
        key   = (league, slate)
        groups.setdefault(key, []).append(e)
    # Keep groups with 2+ edges
    return [edges for edges in groups.values() if len(edges) >= 2]


def _infer_league(ticker: str) -> Optional[str]:
    t = (ticker or "").upper()
    for pfx, name in (("KXMLB","mlb"), ("KXNBA","nba"), ("KXNFL","nfl"),
                      ("KXNHL","nhl"), ("KXUFC","ufc")):
        if t.startswith(pfx):
            return name
    return None


def _slate_key(ticker: str) -> str:
    """
    Pull a date-ish chunk out of the Kalshi sports ticker so we can bucket
    "same slate" together.  Example: 'KXMLBGAME-26OCT14LADMIL-LAD' → '26OCT14'.
    Falls back to the whole ticker if no match (will just not group).
    """
    import re
    m = re.search(r"(\d{2}[A-Z]{3}\d{2})", (ticker or "").upper())
    return m.group(1) if m else "unknown"


# ── Combined probability + edge math ────────────────────────────────────────
def _combo_prob(edges: list) -> float:
    """Independent-event approximation of combined win prob for YES legs.
    Over same-day same-sport correlated unders this UNDER-estimates (good:
    it stays conservative; if it still clears MIN_PARLAY_EDGE_PCT the parlay
    is +EV under even uncorrelated assumption)."""
    p = 1.0
    for e in edges:
        tp = getattr(e, "true_prob", 0) or 0
        p *= tp
    return p


def _combo_implied_price(edges: list) -> float:
    """
    Kalshi quotes the combo as a single market; without that quote we
    estimate it as the product of each leg's implied prob. Real combo
    orders will clamp to the real ask, so this is used only to screen
    whether the parlay is worth attempting at all.
    """
    p = 1.0
    for e in edges:
        imp = getattr(e, "implied_prob", 0) or 0
        p *= imp
    return p


# ── Public: pick parlay-worthy bundles ──────────────────────────────────────
def pick_parlays(edges: list) -> list:
    """
    Returns a list of {legs, combo_prob, combo_price, edge_pct, bundle_key}
    for the top MAX_LEGS-sized bundles that pass every rule. Empty list
    means no parlay should fire this scan.
    """
    if not getattr(config, "PARLAY_LIVE", False):
        return []
    if not edges:
        return []
    good = []
    for group in _group_candidates(edges):
        # take up to MAX_LEGS strongest legs in the group
        group_sorted = sorted(group, key=lambda e: getattr(e, "edge_pct", 0), reverse=True)
        legs = group_sorted[:MAX_LEGS]
        if len(legs) < 2:
            continue
        p   = _combo_prob(legs)
        imp = _combo_implied_price(legs)
        if imp <= 0 or imp >= 1:
            continue
        edge_pct = (p - imp) * 100
        if edge_pct < MIN_PARLAY_EDGE_PCT:
            continue
        good.append({
            "legs":       legs,
            "combo_prob": round(p,   4),
            "combo_price":round(imp, 4),
            "edge_pct":   round(edge_pct, 1),
            "bundle_key": (
                getattr(legs[0], "league", "?") + "-" + _slate_key(getattr(legs[0], "ticker",""))
            ),
        })
    return sorted(good, key=lambda x: x["edge_pct"], reverse=True)


# ── Firing a parlay (gated at every step) ───────────────────────────────────
def fire_parlay(api, bundle: dict, bankroll_total: float) -> dict:
    """
    Attempt to execute a parlay. Gated at every single step.
    Returns {placed, reason, dry_run, ...}.

    NOTE: creating a combo market on Kalshi requires a valid
    collection_ticker that groups the chosen legs. Discovery of
    which collection applies for a given sport/slate requires live
    testing — this function queries list_combo_collections and
    picks the first that references all legs' event_tickers.
    """
    if not getattr(config, "PARLAY_LIVE", False):
        return {"placed": False, "reason": "parlay_live_off"}
    if config.DRY_RUN:
        log(f"PARLAY DRY RUN 🔵 bundle_key={bundle['bundle_key']} legs={len(bundle['legs'])} "
            f"combo={bundle['combo_price']:.2%} model={bundle['combo_prob']:.2%} edge={bundle['edge_pct']:+.1f}%",
            "INFO")
        return {"placed": False, "reason": "dry_run", "dry_run": True}

    # Find a collection that contains every leg's event_ticker
    legs_meta = [{"event_ticker": getattr(e, "event_ticker", None) or _event_from_ticker(e.ticker),
                  "market_ticker": e.ticker,
                  "side":          "yes" if e.direction == "YES" else "no"}
                 for e in bundle["legs"]]
    needed_events = {l["event_ticker"] for l in legs_meta if l["event_ticker"]}
    if not needed_events:
        return {"placed": False, "reason": "no_event_tickers_known"}

    try:
        collections = api.list_combo_collections(limit=100, pages=3)
    except Exception as exc:
        return {"placed": False, "reason": f"collections_lookup_failed: {exc}"}

    chosen = None
    for c in collections:
        covered = set(c.get("event_tickers", []) or [])
        if needed_events.issubset(covered):
            chosen = c
            break
    if not chosen:
        return {"placed": False, "reason": "no_matching_collection"}

    # Size — 1.5% of bankroll, divided per-leg isn't needed since Kalshi quotes
    # the combo as one market. Count = floor(bankroll * pct / combo_price_cents * 100)
    dollars    = round(bankroll_total * PARLAY_PCT_OF_BANKROLL, 2)
    price_cent = max(1, int(round(bundle["combo_price"] * 100)))
    count      = max(1, int(dollars / (price_cent / 100)))

    try:
        result = api.place_parlay(
            collection_ticker = chosen.get("ticker") or chosen.get("collection_ticker"),
            legs              = legs_meta,
            count             = count,
            max_price_cents   = price_cent + 2,   # tolerate 2¢ slippage
        )
    except Exception as exc:
        log(f"PARLAY ERROR {bundle['bundle_key']}: {exc}", "ERROR")
        return {"placed": False, "reason": str(exc)}

    log(f"PARLAY ✅ {bundle['bundle_key']} legs={len(legs_meta)} count={count} "
        f"~${dollars:.2f} combo_ticker={result.get('combo_ticker')}  edge={bundle['edge_pct']:+.1f}%",
        "INFO")
    return {"placed": True, "dollars": dollars, **result}


def _event_from_ticker(ticker: str) -> Optional[str]:
    """Kalshi market tickers are `EVENT-OUTCOME`; event ticker is the
    piece before the last '-'. Fallback heuristic only — if the scanner
    already carries event_ticker on the edge, use that instead."""
    if not ticker or "-" not in ticker:
        return None
    return ticker.rsplit("-", 1)[0]
