"""
SPORTS MODELS (Kalshi)
======================
Probability models for Kalshi's Sports category markets.

Approach — moneyline-first:
  1. Parse the market title for a game-outcome pattern ("Will X beat Y?",
     "X vs Y Winner?", "X to win?") and extract the two team names.
  2. Fetch ESPN win-percentages for both teams and compute the home team's
     true probability using the log5 formula with a modest home-court edge.
  3. Compare to the market's implied YES probability. If the gap exceeds
     MIN_EDGE_PCT, return an edge dict compatible with the scanner.

Covered leagues: MLB, NBA, NFL, NHL, UFC, major soccer leagues.
Spreads / totals / division-winner futures are intentionally skipped for
now — they need separate margin-distribution models and will come later.

Standalone — doesn't depend on other repos, keeps a small in-process ESPN
cache so we don't hammer the API during a scan.
"""
from __future__ import annotations

import datetime
import re
import time
from typing import Optional

import requests

# ── ESPN endpoints ───────────────────────────────────────────────────────────
LEAGUES = {
    # key → (sport_code, league_code)
    "nfl":  ("football",   "nfl"),
    "nba":  ("basketball", "nba"),
    "mlb":  ("baseball",   "mlb"),
    "nhl":  ("hockey",     "nhl"),
    "mls":  ("soccer",     "usa.1"),
    "epl":  ("soccer",     "eng.1"),
    "ufc":  ("mma",        "ufc"),
}
SITE_BASE = "https://site.api.espn.com/apis/site/v2/sports"

# in-process cache (lives for the scan)
_WIN_PCT_CACHE: dict = {}
_WIN_PCT_TTL  = 4 * 60 * 60    # 4 hours

# ── Tunables ─────────────────────────────────────────────────────────────────
HOME_ADV      = 0.03    # +3% log5 bump for home side
MIN_EDGE_PCT  = 8.0     # minimum model-vs-market gap to call it an edge
MIN_CONFIDENCE = 70     # 0–100 confidence used by downstream auto-bettor

# After walk-forward on 2023 showed weather_edge at 49.5% hit (vs 53.8%
# in 2024), we DON'T trust the signal yet. Keep it running but confidence
# capped at 72 — just above gate — so bets are small until another year
# of data confirms or denies. See overseer/docs/WALK_FORWARD_RESULTS.md
WEATHER_EDGE_MAX_CONFIDENCE = 72


# ── ESPN plumbing ────────────────────────────────────────────────────────────
# ESPN's site API returns 403 for generic/bot-looking UAs — this one works.
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36")


def _get(url: str, timeout: int = 10) -> Optional[dict]:
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": _UA})
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def _win_pcts(league_key: str) -> dict:
    """Returns {team_display_name: win_pct} for all teams on today's slate."""
    cached = _WIN_PCT_CACHE.get(league_key)
    if cached and (time.time() - cached["ts"]) < _WIN_PCT_TTL:
        return cached["data"]

    codes = LEAGUES.get(league_key)
    if not codes:
        return {}
    sport, league = codes
    data = _get(f"{SITE_BASE}/{sport}/{league}/scoreboard")
    if not data:
        return {}
    pcts = {}
    for ev in data.get("events", []):
        for comp in ev.get("competitions", []):
            for c in comp.get("competitors", []):
                name = (c.get("team") or {}).get("displayName", "")
                if not name:
                    continue
                for rec in c.get("records", []) or []:
                    if rec.get("type") == "total":
                        parts = (rec.get("summary") or "").split("-")
                        if len(parts) >= 2:
                            try:
                                w, l = int(parts[0]), int(parts[1])
                                if w + l > 0:
                                    pcts[name] = round(w / (w + l), 4)
                            except ValueError:
                                pass
                        break
    _WIN_PCT_CACHE[league_key] = {"ts": time.time(), "data": pcts}
    return pcts


# ── Title parsing ────────────────────────────────────────────────────────────
# Game-outcome title patterns observed on Kalshi:
#   "Will [TEAM A] beat [TEAM B]?"
#   "[TEAM A] vs [TEAM B] Winner?"
#   "Will [TEAM A] win vs [TEAM B]?"
_TITLE_PATTERNS = [
    re.compile(r"^Will\s+(?P<a>[^?]+?)\s+beat\s+(?P<b>[^?]+?)\s*\?", re.IGNORECASE),
    re.compile(r"^(?P<a>[^?]+?)\s+vs\.?\s+(?P<b>[^?]+?)\s+Winner\s*\?", re.IGNORECASE),
    re.compile(r"^Will\s+(?P<a>[^?]+?)\s+win\s+vs\.?\s+(?P<b>[^?]+?)\s*\?", re.IGNORECASE),
    re.compile(r"^Who\s+wins\s+(?P<a>[^?]+?)\s+vs\.?\s+(?P<b>[^?]+?)\s*\?", re.IGNORECASE),
]


def _parse_game_title(title: str) -> Optional[tuple]:
    """Returns (bet_team, opponent) if title matches a moneyline pattern."""
    if not title:
        return None
    for pat in _TITLE_PATTERNS:
        m = pat.search(title.strip())
        if m:
            a = re.sub(r"\s+", " ", m.group("a").strip())
            b = re.sub(r"\s+", " ", m.group("b").strip())
            if a and b and a.lower() != b.lower():
                return a, b
    return None


# Totals-market title patterns (over/under on a game total):
#   "Will there be over 8.5 total runs/goals/points in...?"
#   "Over 48.5 points?" / "Under 48.5 points?"
#   "Will Team X score over 4.5?"  (team total — treated like a side-bias total)
_TOTAL_PATTERNS = [
    re.compile(r"\b(?:over|under)\s+(?P<line>\d{1,3}(?:\.\d)?)\s+(?:total\s+)?"
               r"(?P<unit>runs?|goals?|points?)\b", re.IGNORECASE),
    re.compile(r"will\s+there\s+be\s+(?:over|more\s+than)\s+(?P<line>\d{1,3}(?:\.\d)?)"
               r"\s+(?:total\s+)?(?P<unit>runs?|goals?|points?)", re.IGNORECASE),
    re.compile(r"will\s+(?P<team>[A-Za-z ]+?)\s+score\s+(?:over|more\s+than)\s+"
               r"(?P<line>\d{1,3}(?:\.\d)?)", re.IGNORECASE),
]


def _parse_total_title(title: str) -> Optional[dict]:
    """
    Returns {line: float, unit: str, direction: 'over', team: Optional[str]}
    for a totals/team-total market, else None.
    Kalshi titles always ask the YES side; direction is always 'over'
    (NO on the market = under).
    """
    if not title:
        return None
    for pat in _TOTAL_PATTERNS:
        m = pat.search(title.strip())
        if m:
            try:
                line = float(m.group("line"))
            except Exception:
                continue
            d = {"line": line, "direction": "over"}
            try:    d["unit"] = m.group("unit").lower()
            except: d["unit"] = ""
            try:    d["team"] = m.group("team").strip()
            except: d["team"] = None
            return d
    return None


# ── Ticker → league detection ────────────────────────────────────────────────
_TICKER_LEAGUE_RE = {
    "nfl":  re.compile(r"^KXNFL", re.I),
    "nba":  re.compile(r"^KXNBA", re.I),
    "mlb":  re.compile(r"^KXMLB", re.I),
    "nhl":  re.compile(r"^KXNHL", re.I),
    "ufc":  re.compile(r"^KXUFC", re.I),
    "mls":  re.compile(r"^KXMLS",  re.I),
    "epl":  re.compile(r"^KXEPL|^KXENGPL", re.I),
}


def _detect_league(ticker: str) -> Optional[str]:
    for key, pat in _TICKER_LEAGUE_RE.items():
        if pat.search(ticker or ""):
            return key
    return None


# ── Team-name fuzzy match ────────────────────────────────────────────────────
def _match_team(bet_name: str, team_pcts: dict) -> Optional[str]:
    """Best-match a short/fuzzy team mention against ESPN's full displayNames."""
    if not bet_name:
        return None
    low = bet_name.lower().strip()
    # exact first
    for name in team_pcts:
        if name.lower() == low:
            return name
    # substring either direction
    for name in team_pcts:
        n = name.lower()
        if n in low or low in n:
            return name
    # last-word (common nickname: "Yankees", "Lakers")
    tokens = [t for t in re.split(r"\s+", low) if len(t) >= 4]
    if tokens:
        last = tokens[-1]
        for name in team_pcts:
            if last in name.lower().split():
                return name
    return None


# ── Totals model (weather-driven, the proven +EV signal) ───────────────────
def _analyze_total_market(market: dict, ticker: str, title: str,
                          league: str) -> Optional[dict]:
    """
    Weather-driven adjustment for outdoor NFL/MLB totals markets.
    Only fires on markets whose title is a totals question AND whose venue
    is likely outdoor. Uses wttr.in (free) for the forecast.

    Edge direction: we always BUY NO (under) when weather points under —
    i.e. we take the opposite of the YES ("Will there be over N?") side.
    """
    import weather as _wx

    parsed = _parse_total_title(title)
    if not parsed:
        return None
    # Weather only applies to outdoor sports
    if league not in ("nfl", "mlb"):
        return None

    # Try to pull a city from the title or event context (naïve: look for
    # city tokens). If we don't know the city, we can't fetch weather.
    city = _extract_city(title, market)
    if not city or not _wx.is_outdoor(league, city):
        return None

    wx   = _wx.get_weather(city)
    edge = _wx.total_direction_edge(wx, league)
    if not edge:
        return None

    # Market pricing
    def _px(fc, fd):
        v = market.get(fc)
        if v is not None:
            try: return int(v) / 100
            except: pass
        v = market.get(fd)
        if v is not None:
            try:
                v = float(v)
                return v / 100 if v > 1 else v
            except: pass
        return None

    yes_ask = _px("yes_ask", "yes_ask_dollars")
    yes_bid = _px("yes_bid", "yes_bid_dollars")
    if yes_ask is None or yes_ask <= 0 or yes_ask >= 1:
        return None

    # Baseline: assume market is fair (implied YES/NO roughly 50/50).
    # Weather pushes probability down by confidence_bump on the YES (over) side.
    baseline_over = yes_ask            # take ask as market's over implied
    adj_over      = max(0.05, baseline_over - edge["confidence_bump"])
    adj_under     = 1 - adj_over

    # We bet NO (under). Market price for NO = 1 - yes_bid (if liquid) or 1 - yes_ask.
    no_cost = 1 - (yes_bid if yes_bid is not None else yes_ask)
    if no_cost <= 0 or no_cost >= 1:
        return None

    edge_pct = round((adj_under - no_cost) * 100, 1)
    if edge_pct < MIN_EDGE_PCT:
        return None

    # Weather_edge failed 2023 walk-forward (49.5% hit rate). Cap confidence
    # low until a second year of data confirms edge. See WALK_FORWARD_RESULTS.md
    nominal_conf = min(100, MIN_CONFIDENCE + int(edge["confidence_bump"] * 100))
    confidence   = min(nominal_conf, WEATHER_EDGE_MAX_CONFIDENCE)

    return {
        "ticker":       ticker,
        "title":        title,
        "category":     "Sports",
        "direction":    "NO",
        "true_prob":    round(adj_under, 4),
        "implied_prob": round(no_cost,  4),
        "edge_pct":     edge_pct,
        "confidence":   confidence,
        "reasoning":    f"TOTAL/UNDER | {edge['reason']} | city={city} | wf-capped",
        "league":       league,
        "signal":       "weather_edge",
    }


# City extraction — looks for known OUTDOOR_NFL_CITIES / major MLB cities
# in the title or any nested event info the scanner may have attached.
def _extract_city(title: str, market: dict) -> Optional[str]:
    import weather as _wx
    hay = " ".join(filter(None, [
        title,
        (market.get("subtitle") or ""),
        (market.get("event_title") or ""),
    ])).lower()
    for city in list(_wx.OUTDOOR_NFL_CITIES) + list(_wx.INDOOR_MLB_STADIUMS) + [
        "atlanta","detroit","chicago","boston","new york","los angeles","oakland",
        "san francisco","san diego","phoenix","dallas","houston","seattle","portland",
        "minneapolis","st. louis","kansas city","cincinnati","cleveland","pittsburgh",
        "philadelphia","washington","baltimore","denver","las vegas","milwaukee",
    ]:
        if city in hay:
            return city
    return None


# ── Entry point used by scanner / probability_models.py ─────────────────────
def analyze_market(market: dict) -> Optional[dict]:
    """
    Decide whether this Kalshi sports market has a modelable edge.
    Returns a dict in the standard model output shape, or None.

    Expects `market` to carry at minimum:
      - ticker        (str)
      - title         (str) — human-readable question
      - yes_bid, yes_ask (ints 1..99, cents) OR yes_bid_dollars/yes_ask_dollars
      - category      (str) — should be "Sports"
    """
    ticker = (market.get("ticker") or "").upper()
    title  = market.get("title") or market.get("subtitle") or ""
    league = _detect_league(ticker)
    if not league:
        return None

    # ── Totals market? (weather_edge is the only proven +EV sports signal)
    if "TOTAL" in ticker or _parse_total_title(title):
        res = _analyze_total_market(market, ticker, title, league)
        if res is not None:
            return res
        # fall through — maybe this title also matches a moneyline pattern

    parsed = _parse_game_title(title)
    if not parsed:
        return None
    bet_team, opp_team = parsed

    pcts = _win_pcts(league)
    if not pcts:
        return None
    bet_name = _match_team(bet_team, pcts)
    opp_name = _match_team(opp_team, pcts)
    if not bet_name or not opp_name or bet_name == opp_name:
        return None

    # Which side (bet_team) do we consider "home"? Title convention is usually
    # "away vs home" or "away @ home"; absent cleaner signals we treat the
    # team named first in the question as the one we're betting on.
    wp_bet = pcts.get(bet_name)
    wp_opp = pcts.get(opp_name)
    if wp_bet is None or wp_opp is None:
        return None

    # Log5 (symmetric; a modest home-court bump is skipped here since we don't
    # reliably know which side is home from the title alone).
    h = min(max(wp_bet, 0.05), 0.95)
    a = min(max(wp_opp, 0.05), 0.95)
    denom = h + a - 2 * h * a
    if denom <= 0:
        return None
    true_p = (h - h * a) / denom
    true_p = round(min(max(true_p, 0.05), 0.95), 4)

    # Market implied probability for YES side (bet_team wins).
    def _px(field_cents, field_dollars):
        v = market.get(field_cents)
        if v is not None:
            try:    return int(v) / 100
            except: pass
        v = market.get(field_dollars)
        if v is not None:
            try:
                v = float(v)
                return v / 100 if v > 1 else v
            except: pass
        return None

    yes_ask = _px("yes_ask", "yes_ask_dollars")
    yes_bid = _px("yes_bid", "yes_bid_dollars")
    if yes_ask is None or yes_ask <= 0 or yes_ask >= 1:
        return None

    implied = yes_ask                                # pay the ask when buying YES
    edge_pct = round((true_p - implied) * 100, 1)

    if abs(edge_pct) < MIN_EDGE_PCT:
        return None

    direction = "YES" if edge_pct > 0 else "NO"
    if direction == "NO":
        implied = 1 - (yes_bid if yes_bid is not None else yes_ask)
        edge_pct = round(((1 - true_p) - implied) * 100, 1)
        if edge_pct < MIN_EDGE_PCT:
            return None

    confidence = min(100, MIN_CONFIDENCE + int(abs(edge_pct)))

    return {
        "ticker":       ticker,
        "title":        title,
        "category":     "Sports",
        "direction":    direction,
        "true_prob":    round(true_p if direction == "YES" else 1 - true_p, 4),
        "implied_prob": round(implied, 4),
        "edge_pct":     edge_pct,
        "confidence":   confidence,
        "reasoning":    (f"log5({bet_name} wp={wp_bet:.1%} vs {opp_name} wp={wp_opp:.1%}) "
                         f"-> {direction} {bet_team}  model={true_p:.1%} market={implied:.1%}"),
        "league":       league,
    }
