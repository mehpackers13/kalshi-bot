"""
prop_projection: our own player-prop model, independent of the sportsbook.

Kalshi "N+ <stat>" markets (NBA pts/reb/ast/3pt/PRA, NHL pts/ast/goals, NFL rec/rush/pass yds, TDs).

Model
-----
* Data: ESPN per-game game log for the current regular season (site.web.api.espn.com .../gamelog),
  cached in data/espn_player_stats.json (24h TTL, last 20 games, at most MAX_NEW_FETCHES=60 new
  fetches per scan).  Needs >= 6 games played.
* Mean: exponentially weighted per-game mean (half-life 10 games, newest weighted most).
* Distribution: negative binomial matched to that mean with a stated dispersion assumption
  (variance = DISP_IDX * mean for counting stats; sd = CV * mean for yardage stats); the
  dispersion constants below are round-number assumptions from typical box-score variance, NOT
  fitted.  P(X >= N) comes from the NB survival function.
* Blend: p = 0.75 * p_NB + 0.25 * empirical share of games with X >= N (Laplace-smoothed),
  when >= 8 games are available.
* Guards: skip players on ESPN's league injury list (any status), skip games that have started,
  skip if our p is > 0.35 away from the Kalshi mid (almost always information we lack:
  injury/rest/role), require 1c <= bid, ask <= 99c, spread <= 10c.
* Edge: edge_yes = p - (ask + fee), edge_no = (1-p) - ((1-bid) + fee); enter the better side
  when >= 0.08.  model_prob = p (probability YES wins).
Not modelled: opponent strength, pace, minutes changes, back-to-backs.
"""
from __future__ import annotations

import datetime
import json
import math
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

import sports_match as sm
import sportsbook as sb

NAME = "prop_projection"
CAP = 20
MIN_EDGE = 0.08
MAX_NEW_FETCHES = 60
TTL = 24 * 3600
STALE_OK = 7 * 86400
MIN_GAMES = 6
HALF_LIFE = 10.0
MAX_DISAGREE = 0.35
MAX_SPREAD_C = 10
PER_EVENT = 3
STATS_FILE = Path(__file__).resolve().parent.parent / "data" / "espn_player_stats.json"

# label -> ("idx", d)  variance = d * mean      |   ("cv", c)  sd = c * mean
DISPERSION = {
    "points": ("idx", 2.4), "rebounds": ("idx", 1.5), "assists": ("idx", 1.5), "threes": ("idx", 1.25),
    "pra": ("idx", 3.2),
    "nhl_points": ("idx", 1.1), "nhl_assists": ("idx", 1.05), "goals": ("idx", 1.0),
    "rec_yds": ("cv", 0.85), "rush_yds": ("cv", 0.85), "pass_yds": ("cv", 0.30),
    "pass_td": ("idx", 1.0), "td": ("idx", 1.0),
}
# league -> label -> list of ESPN gamelog column names summed (first '-' part used for "made-att")
COLUMNS = {
    "NBA": {"points": ["points"], "rebounds": ["totalRebounds"], "assists": ["assists"],
            "threes": ["threePointFieldGoalsMade-threePointFieldGoalsAttempted"],
            "pra": ["points", "totalRebounds", "assists"]},
    "NHL": {"nhl_points": ["points"], "nhl_assists": ["assists"], "goals": ["goals"]},
    "NFL": {"rec_yds": ["receivingYards"], "rush_yds": ["rushingYards"], "pass_yds": ["passingYards"],
            "pass_td": ["passingTouchdowns"], "td": ["receivingTouchdowns", "rushingTouchdowns"]},
}
COLUMNS["WNBA"] = COLUMNS["NBA"]
# Kalshi spec label (sports_match.PROPS) -> our label
LABEL_MAP = {("NHL", "points"): "nhl_points", ("NHL", "assists"): "nhl_assists"}
UNIT = {"points": "pts", "rebounds": "reb", "assists": "ast", "threes": "3pm", "pra": "pra",
        "nhl_points": "pts", "nhl_assists": "ast", "goals": "goals", "rec_yds": "rec yds",
        "rush_yds": "rush yds", "pass_yds": "pass yds", "pass_td": "pass td", "td": "td"}

REASONS = Counter()
LAST = {}
_store = None
_injured = {}   # league -> set of athlete ids


# ------------------------------------------------------------------ distribution
def nb_sf(k: int, mean: float, var: float) -> float:
    """P(X >= k) for a negative binomial with the given mean/variance (Poisson if var<=mean)."""
    if k <= 0:
        return 1.0
    if mean <= 0:
        return 0.0
    if var <= mean * 1.0001:               # Poisson
        term, cdf = math.exp(-mean), 0.0
        for x in range(0, k):
            cdf += term
            term *= mean / (x + 1)
        return max(0.0, 1.0 - cdf)
    r = mean * mean / (var - mean)
    p = r / (r + mean)                     # success prob in scipy convention
    lp = math.lgamma
    cdf = 0.0
    for x in range(0, k):
        cdf += math.exp(lp(x + r) - lp(r) - lp(x + 1) + r * math.log(p) + x * math.log(1 - p))
        if cdf >= 1.0:
            return 0.0
    return max(0.0, 1.0 - cdf)


def project(samples, label, k):
    """samples oldest->newest list of per-game values. -> (p, mean) or None."""
    n = len(samples)
    if n < MIN_GAMES:
        return None
    ws = [0.5 ** ((n - 1 - i) / HALF_LIFE) for i in range(n)]
    mean = sum(w * x for w, x in zip(ws, samples)) / sum(ws)
    if mean <= 0:
        return 0.0, mean
    kind, c = DISPERSION[label]
    var = c * mean if kind == "idx" else (c * mean) ** 2
    p = nb_sf(int(math.ceil(k)), mean, var)
    if n >= 8:
        emp = (sum(1 for x in samples if x >= k) + 0.5) / (n + 1.0)
        p = 0.75 * p + 0.25 * emp
    return min(0.99, max(0.01, p)), mean


# ------------------------------------------------------------------ data
def _load():
    global _store
    if _store is None:
        try:
            _store = json.loads(STATS_FILE.read_text())
        except Exception:
            _store = {}
        _store.setdefault("players", {})
    return _store


def save():
    if _store is not None:
        try:
            STATS_FILE.parent.mkdir(exist_ok=True)
            STATS_FILE.write_text(json.dumps(_store, separators=(",", ":")))
        except Exception:
            pass


def _parse_gamelog(league, d):
    """-> {label: [values oldest..newest]} for the current regular season, or None."""
    names = d.get("names") or []
    sts = d.get("seasonTypes") or []
    cur = None
    for st in sts:
        if "Regular" in st.get("displayName", ""):
            cur = st
            break
    if not cur or not names:
        return None
    evmeta = d.get("events") or {}
    rows = []
    for cat in cur.get("categories", []):
        for ev in cat.get("events", []):
            meta = evmeta.get(str(ev.get("eventId")), {})
            rows.append((meta.get("gameDate", ""), ev.get("stats", [])))
    rows.sort(key=lambda r: r[0])
    idx = {n: i for i, n in enumerate(names)}
    out = {}
    for label, cols in COLUMNS[league].items():
        if any(c not in idx for c in cols):
            continue
        vals = []
        for _, st in rows:
            try:
                tot = 0.0
                for c in cols:
                    v = str(st[idx[c]]).split("-")[0]
                    tot += float(v)
                vals.append(tot)
            except Exception:
                continue
        out[label] = vals[-20:]
    return out or None


def _fetch(league, aid):
    if requests is None:
        return None
    sport, slug = sb.LEAGUES[league][:2]
    try:
        r = requests.get(f"https://site.web.api.espn.com/apis/common/v3/sports/{sport}/{slug}/athletes/{aid}/gamelog",
                         headers=sb.UA, timeout=20)
        if r.status_code != 200:
            return None
        return _parse_gamelog(league, r.json())
    except Exception:
        return None


def _ensure_stats(pairs):
    """pairs: ordered unique [(league, aid)]. Fetch stale/missing ones, <= MAX_NEW_FETCHES."""
    S = _load()["players"]
    now = time.time()
    todo = [(lg, a) for lg, a in pairs if now - S.get(f"{lg}:{a}", {}).get("ts", 0) > TTL][:MAX_NEW_FETCHES]
    if todo:
        with ThreadPoolExecutor(max_workers=8) as ex:
            res = list(ex.map(lambda p: _fetch(*p), todo))
        for (lg, a), r in zip(todo, res):
            if r:
                S[f"{lg}:{a}"] = {"ts": int(now), "s": r}
            elif f"{lg}:{a}" not in S:
                S[f"{lg}:{a}"] = {"ts": int(now) - TTL + 3600, "s": {}}   # negative cache for 1h
    LAST["stat_fetches"] = len(todo)
    return S


def _load_injured(league):
    if league in _injured:
        return _injured[league]
    ids = set()
    if requests is not None:
        sport, slug = sb.LEAGUES[league][:2]
        try:
            r = requests.get(f"{sb.SITE}/{sport}/{slug}/injuries", headers=sb.UA, timeout=20)
            if r.status_code == 200:
                for t in r.json().get("injuries", []):
                    for i in t.get("injuries", []):
                        a = (i.get("athlete") or {}).get("id")
                        if a:
                            ids.add(str(a))
        except Exception:
            pass
    _injured[league] = ids
    return ids


# ------------------------------------------------------------------ rule
def select(ctx) -> list:
    now = ctx.get("now") or datetime.datetime.utcnow()
    REASONS.clear()
    LAST.clear()
    cands = []
    for m in ctx["markets"]:
        s = m.get("series")
        info = sm.SERIES.get(s)
        if not info or info[1] != "prop" or info[0] not in COLUMNS:
            continue
        if not (0 < (m.get("hours_to_close") or 0) <= 168):
            continue
        if m.get("yes_bid", 0) < 1 or m.get("yes_ask", 100) > 99 or m["yes_ask"] - m["yes_bid"] > MAX_SPREAD_C:
            continue
        cands.append(m)
    LAST["candidates"] = len(cands)
    if not cands:
        return []
    sm.prepare(cands, odds=False, props=False)
    resolved = []
    for m in cands:
        rp = sm.resolve_player(m)
        if not rp:
            REASONS["unresolved"] += 1
            continue
        if rp["event"]["start"] <= now + datetime.timedelta(minutes=5):
            REASONS["started"] += 1
            continue
        lab = rp["spec"][0]
        label = LABEL_MAP.get((rp["league"], lab), lab)
        if label not in COLUMNS[rp["league"]]:
            REASONS["stat_unsupported"] += 1
            continue
        resolved.append((m, rp, label))
    LAST["resolved"] = len(resolved)
    order, seen = [], set()
    for m, rp, label in sorted(resolved, key=lambda x: x[1]["event"]["start"]):
        k = (rp["league"], rp["aid"])
        if k not in seen:
            seen.add(k)
            order.append(k)
    S = _ensure_stats(order)
    out = []
    for m, rp, label in resolved:
        lg, aid = rp["league"], rp["aid"]
        if aid in _load_injured(lg):
            REASONS["injury_listed"] += 1
            continue
        ent = S.get(f"{lg}:{aid}")
        if not ent or time.time() - ent.get("ts", 0) > STALE_OK or label not in ent.get("s", {}):
            REASONS["no_stats"] += 1
            continue
        res = project(ent["s"][label], label, rp["threshold"])
        if res is None:
            REASONS["few_games"] += 1
            continue
        p, mean = res
        bid, ask = m["yes_bid"] / 100.0, m["yes_ask"] / 100.0
        if abs(p - (bid + ask) / 2) > MAX_DISAGREE:
            REASONS["too_far_from_market"] += 1
            continue
        e_yes = p - (ask + sm.fee(ask))
        e_no = (1 - p) - ((1 - bid) + sm.fee(1 - bid))
        side, edge = ("YES", e_yes) if e_yes >= e_no else ("NO", e_no)
        if edge < MIN_EDGE:
            REASONS["edge_small"] += 1
            continue
        n = len(ent["s"][label])
        notes = f"proj {mean:.1f} {UNIT[label]}/g, line {rp['threshold'] - 0.5:g}, p={p:.2f} n={n} | edge {edge:.2f}"
        out.append({"ticker": m["ticker"], "side": side, "category": m.get("category") or "Sports",
                    "event": m.get("event") or "-".join(m["ticker"].split("-")[:2]),
                    "series": m.get("series"), "model_prob": round(p, 4),
                    "notes": notes[:120].replace(",", ";"), "_edge": edge})
    out.sort(key=lambda e: -e["_edge"])
    per, final = {}, []
    for e in out:
        n = per.get(e["event"], 0)
        if n >= PER_EVENT:
            continue
        per[e["event"]] = n + 1
        final.append(e)
        if len(final) >= CAP:
            break
    for e in final:
        e.pop("_edge", None)
    LAST.update({"edges": len(out), "entered": len(final)})
    save()
    sb.save_athletes()
    return final
