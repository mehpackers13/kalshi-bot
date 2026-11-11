"""
Free sportsbook reference prices: ESPN scoreboard + ESPN core odds feed (DraftKings, provider 100).

No keys needed. Everything is cached per process; athlete names are cached on disk in
data/espn_athletes.json (roster calls are the only expensive part, cached 14 days per team).
Total ESPN calls per process are capped (MAX_CALLS) so a scan stays under ~250 requests;
403/404/timeouts return None quietly.

Data shapes (verified live 2026-11-11)
--------------------------------------
Scoreboard   site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard?dates=YYYYMMDD
             (date RANGES return HTTP 400, so we query one day at a time).  The scoreboard
             `odds` block differs by sport (NHL/NCAAB often empty), so game odds always come
             from the core odds endpoint instead.
Game odds    sports.core.api.espn.com/v2/sports/{sport}/leagues/{league}/events/{id}/competitions/{id}/odds/100
             homeTeamOdds/awayTeamOdds .current.moneyLine.american, .current.pointSpread.american (signed
             line for THAT team), .current.spread.american (price), same under .open;
             top level overUnder/overOdds/underOdds (+ open.over/under/total);
             soccer adds drawOdds.moneyLine (three-way market).
Props        .../odds/100/propBets?limit=1000&page=N  (pageCount in the envelope; ~1,160 NBA lines)
             Item shapes:
               (a) OVER/UNDER PAIR  type "Total Points", "Total Rebounds", "Team Total Points",
                   "Total Receiving Yards (incl. overtime)" ...: TWO items with identical
                   athlete/team + line (odds.total.value / current.target.value); the items carry
                   NO over/under label.  Convention used here: the FIRST item is the OVER, the
                   second the UNDER.  Checked against the milestone ladder of the same player in
                   one NBA game: consistent in 9 of 11 pairs (see research/sportsbook_probe.py),
                   so pair-derived probabilities are flagged approx=True.
               (b) MILESTONE (one-sided "N+") type "... Milestones": one item per rung,
                   odds.total.value = "15+", current.target.value = 15.0.  Price is for
                   X >= 15.  No opposite side exists -> flat margin removal (approx=True).
               (c) ONE-SIDED YES types: "Anytime Touchdown Scorer", "To Record a Double Double",
                   "Player to score 2 or more touchdowns"... no line, athlete only.
               (d) SOCCER schema: the price lives under current.over.american (+ current.target.value);
                   "Team Total Goals" is a one-sided ladder of over lines; "Both Teams To Score"
                   is two unlabeled items (yes/no order unknown) -> NOT used.
Athlete ids  item.athlete.$ref ends in /athletes/{id}; names from site.api .../teams/{id}/roster.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

try:
    from logger import log
except Exception:  # pragma: no cover
    def log(msg, level="INFO"):
        print(msg)

DATA_DIR = Path(__file__).parent / "data"
ATHLETE_FILE = DATA_DIR / "espn_athletes.json"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
SITE = "https://site.api.espn.com/apis/site/v2/sports"
CORE = "https://sports.core.api.espn.com/v2/sports"

MAX_CALLS = 250          # hard cap on ESPN requests per process
ROSTER_TTL = 14 * 86400  # roster -> athlete names refresh
FLAT_MARGIN = 0.045      # one-sided lines: remove this much overround

# league key -> (sport, espn slug, scoreboard extra params, has_props)
LEAGUES = {
    "NBA":    ("basketball", "nba", {}, True),
    "NHL":    ("hockey", "nhl", {}, True),
    "NFL":    ("football", "nfl", {}, True),
    "NCAAF":  ("football", "college-football", {"groups": 80, "limit": 400}, False),
    "NCAAB":  ("basketball", "mens-college-basketball", {"groups": 50, "limit": 400}, False),
    "WNBA":   ("basketball", "wnba", {}, True),
    "MLB":    ("baseball", "mlb", {}, True),
    "EPL":    ("soccer", "eng.1", {}, True),
    "LALIGA": ("soccer", "esp.1", {}, True),
    "BUNDESLIGA": ("soccer", "ger.1", {}, True),
    "SERIEA": ("soccer", "ita.1", {}, True),
    "LIGUE1": ("soccer", "fra.1", {}, True),
    "UCL":    ("soccer", "uefa.champions", {}, True),
    "MLS":    ("soccer", "usa.1", {}, True),
    "LIGAMX": ("soccer", "mex.1", {}, True),
}
SOCCER = {k for k, v in LEAGUES.items() if v[0] == "soccer"}

_calls = 0
_lock = threading.Lock()
_cache = {}              # url+params -> json (per process)
_athletes = None         # loaded lazily from disk
_athletes_dirty = False
_events = {}             # (league, yyyymmdd) -> [event dicts]
_event_by_id = {}        # (league, id) -> event dict


def calls_used() -> int:
    return _calls


def reset_budget(max_calls=None):
    global _calls, MAX_CALLS
    _calls = 0
    if max_calls:
        MAX_CALLS = max_calls


def _get(url, params=None):
    """GET json with per-process cache, call budget, quiet failure. Thread-safe."""
    global _calls
    if requests is None:
        return None
    key = url + "?" + json.dumps(params or {}, sort_keys=True)
    with _lock:
        if key in _cache:
            return _cache[key]
        if _calls >= MAX_CALLS:
            return None
        _calls += 1
    try:
        r = requests.get(url, params=params, headers=UA, timeout=20)
        data = r.json() if r.status_code == 200 else None
    except Exception:
        data = None
    with _lock:
        _cache[key] = data
    return data


def prefetch(jobs, workers=8):
    """Warm the cache for [(url, params), ...] in parallel (respects the call budget)."""
    jobs = [j for j in jobs if (j[0] + "?" + json.dumps(j[1] or {}, sort_keys=True)) not in _cache]
    if not jobs:
        return
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(lambda j: _get(j[0], j[1]), jobs))


def prefetch_scoreboards(pairs):
    """pairs: iterable of (league, date). One parallel batch, then get_scoreboard() is free."""
    jobs = []
    for lg, day in pairs:
        sport, slug, extra, _ = LEAGUES[lg]
        params = {"dates": day.strftime("%Y%m%d")}
        params.update(extra)
        jobs.append((f"{SITE}/{sport}/{slug}/scoreboard", params))
    prefetch(jobs)


def prefetch_odds(events):
    # events without a scoreboard `odds` block never have core odds either (checked: 0 exceptions in
    # 5 leagues / 330 events), so skip them and save the 404 call
    prefetch([(_event_base(e), None) for e in events if not e["game_loaded"] and e.get("sb_odds")])


def prefetch_rosters(events):
    """Warm roster calls for teams whose roster is not cached (parallel)."""
    A = _load_athletes()
    jobs, seen = [], set()
    for e in events:
        for side in ("home", "away"):
            k = f"{e['league']}:{e[side]['id']}"
            ts = A["rosters"].get(k)
            if k in seen or (ts and time.time() - ts < ROSTER_TTL):
                continue
            seen.add(k)
            sport, slug = LEAGUES[e["league"]][:2]
            jobs.append((f"{SITE}/{sport}/{slug}/teams/{e[side]['id']}/roster", None))
    prefetch(jobs)


def prefetch_props(events):
    prefetch([(_event_base(e) + "/propBets", {"limit": 1000, "page": 1}) for e in events
              if not e["props_loaded"] and LEAGUES[e["league"]][3]])


# ---------------------------------------------------------------- time helpers
def _us_dst(utc: datetime.datetime) -> bool:
    """US daylight time: second Sunday of March 07:00Z to first Sunday of November 06:00Z."""
    y = utc.year
    d = datetime.datetime(y, 3, 1)
    d += datetime.timedelta(days=(6 - d.weekday()) % 7 + 7)
    start = d.replace(hour=7)
    d = datetime.datetime(y, 11, 1)
    d += datetime.timedelta(days=(6 - d.weekday()) % 7)
    end = d.replace(hour=6)
    return start <= utc < end


def to_eastern_date(utc: datetime.datetime) -> datetime.date:
    off = -4 if _us_dst(utc) else -5
    return (utc + datetime.timedelta(hours=off)).date()


def parse_espn_time(s: str):
    try:
        return datetime.datetime.strptime(s.replace("Z", ""), "%Y-%m-%dT%H:%M")
    except Exception:
        try:
            return datetime.datetime.strptime(s.replace("Z", "")[:19], "%Y-%m-%dT%H:%M:%S")
        except Exception:
            return None


# ---------------------------------------------------------------- odds maths
def am_to_prob(a):
    """American odds -> raw implied probability (None if unusable)."""
    try:
        a = float(str(a).replace("EVEN", "100").replace("+", ""))
    except Exception:
        return None
    if a == 0:
        return None
    return 100.0 / (a + 100.0) if a > 0 else -a / (-a + 100.0)


def devig_two(a, b):
    """Multiplicative two-way devig: p_a = i_a / (i_a + i_b).  Inputs american odds. -> (p_a, p_b)"""
    ia, ib = am_to_prob(a), am_to_prob(b)
    if ia is None or ib is None:
        return None
    s = ia + ib
    return ia / s, ib / s


def devig_three(a, b, c):
    ps = [am_to_prob(x) for x in (a, b, c)]
    if any(p is None for p in ps):
        return None
    s = sum(ps)
    return tuple(p / s for p in ps)


def devig_one_sided(a, margin=FLAT_MARGIN):
    """One-sided line (milestone / anytime scorer): flat margin removal. Returns (p, approx=True)."""
    p = am_to_prob(a)
    if p is None:
        return None
    return min(0.995, p / (1.0 + margin)), True


def _am(node):
    """Pull an american-odds number from the various ESPN shapes."""
    if node is None:
        return None
    if isinstance(node, (int, float)):
        return float(node)
    if isinstance(node, str):
        try:
            return float(node.replace("+", "").replace("EVEN", "100"))
        except Exception:
            return None
    if isinstance(node, dict):
        for k in ("american", "alternateDisplayValue", "value"):
            if k in node:
                v = _am(node[k])
                if v is not None:
                    return v
    return None


def _num(x):
    try:
        return float(str(x).replace("+", ""))
    except Exception:
        return None


# ---------------------------------------------------------------- athletes cache
def _load_athletes():
    global _athletes
    if _athletes is None:
        try:
            _athletes = json.loads(ATHLETE_FILE.read_text())
        except Exception:
            _athletes = {}
        _athletes.setdefault("players", {})   # id -> {n: name, t: teamId, l: league}
        _athletes.setdefault("rosters", {})   # "league:teamId" -> ts
    return _athletes


def save_athletes():
    global _athletes_dirty
    if _athletes is not None and _athletes_dirty:
        try:
            DATA_DIR.mkdir(exist_ok=True)
            ATHLETE_FILE.write_text(json.dumps(_athletes, separators=(",", ":")))
            _athletes_dirty = False
        except Exception:
            pass


def athlete_name(league, athlete_id):
    p = _load_athletes()["players"].get(f"{league}:{athlete_id}")
    return p["n"] if p else None


def athlete_team(league, athlete_id):
    p = _load_athletes()["players"].get(f"{league}:{athlete_id}")
    return p.get("t") if p else None


def ensure_roster(league, team_id) -> bool:
    """Make sure the roster for a team is cached. Returns True when roster known."""
    global _athletes_dirty
    A = _load_athletes()
    key = f"{league}:{team_id}"
    ts = A["rosters"].get(key)
    if ts and time.time() - ts < ROSTER_TTL:
        return True
    sport, slug = LEAGUES[league][:2]
    d = _get(f"{SITE}/{sport}/{slug}/teams/{team_id}/roster")
    if not d:
        return bool(ts)
    n = 0
    for grp in d.get("athletes", []):
        items = grp.get("items") if isinstance(grp, dict) and "items" in grp else [grp]
        for a in items:
            if not isinstance(a, dict) or "id" not in a:
                continue
            nm = a.get("fullName") or a.get("displayName")
            if nm:
                A["players"][f"{league}:{a['id']}"] = {"n": nm, "t": str(team_id)}
                n += 1
    if n:
        A["rosters"][key] = int(time.time())
        _athletes_dirty = True
    return n > 0


# ---------------------------------------------------------------- events
def _team_block(c):
    t = c.get("team", {})
    return {"id": str(t.get("id", "")), "abbr": t.get("abbreviation", ""),
            "name": t.get("displayName", ""), "short": t.get("shortDisplayName", ""),
            "loc": t.get("location", ""), "nick": t.get("name", "")}


def get_scoreboard(league, day: datetime.date):
    """Events for one US/Eastern calendar day (ESPN's date param). Cached."""
    k = (league, day.strftime("%Y%m%d"))
    if k in _events:
        return _events[k]
    sport, slug, extra, _ = LEAGUES[league]
    params = {"dates": k[1]}
    params.update(extra)
    d = _get(f"{SITE}/{sport}/{slug}/scoreboard", params)
    out = []
    for e in (d or {}).get("events", []):
        try:
            c = e["competitions"][0]
            home = [x for x in c["competitors"] if x.get("homeAway") == "home"][0]
            away = [x for x in c["competitors"] if x.get("homeAway") == "away"][0]
            start = parse_espn_time(e.get("date", ""))
            if not start:
                continue
            ev = {"league": league, "id": str(e["id"]), "start": start,
                  "date_et": to_eastern_date(start), "state": e.get("status", {}).get("type", {}).get("state", ""),
                  "home": _team_block(home), "away": _team_block(away), "name": e.get("name", ""),
                  "sb_odds": bool(c.get("odds")), "game": None, "game_loaded": False, "props": None, "props_loaded": False}
            _event_by_id[(league, ev["id"])] = ev
            out.append(ev)
        except Exception:
            continue
    _events[k] = out
    return out


def get_events(days=4, leagues=None, today=None):
    """Scoreboards for today..today+days (ET), all leagues. ~15*days calls."""
    today = today or to_eastern_date(datetime.datetime.utcnow())
    out = []
    for lg in (leagues or LEAGUES):
        for i in range(-1, days):
            out += get_scoreboard(lg, today + datetime.timedelta(days=i))
    return out


def _event_base(ev):
    sport, slug = LEAGUES[ev["league"]][:2]
    return f"{CORE}/{sport}/leagues/{slug}/events/{ev['id']}/competitions/{ev['id']}/odds/100"


def load_game_odds(ev):
    """Fill ev['game'] = {'ml':{...}, 'spread':{...}, 'total':{...}} (any may be missing)."""
    if ev["game_loaded"]:
        return ev["game"]
    ev["game_loaded"] = True
    if not ev.get("sb_odds"):
        return None
    d = _get(_event_base(ev))
    if not d or "homeTeamOdds" not in d:
        return None
    g = {}
    ho, ao = d.get("homeTeamOdds", {}), d.get("awayTeamOdds", {})

    def cur(t, *path):
        n = t.get("current", {})
        for p in path:
            n = n.get(p, {}) if isinstance(n, dict) else {}
        return _am(n) if path[-1] != "pointSpread" else _num(n.get("american") if isinstance(n, dict) else n)

    def opn(t, *path):
        n = t.get("open", {})
        for p in path:
            n = n.get(p, {}) if isinstance(n, dict) else {}
        return _am(n)

    ml_h = cur(ho, "moneyLine") if ho.get("current") else _am(ho.get("moneyLine"))
    ml_a = cur(ao, "moneyLine") if ao.get("current") else _am(ao.get("moneyLine"))
    if ml_h is not None and ml_a is not None:
        draw = _am((d.get("drawOdds") or {}).get("moneyLine"))
        g["ml"] = {"home": ml_h, "away": ml_a, "draw": draw,
                   "open_home": opn(ho, "moneyLine"), "open_away": opn(ao, "moneyLine")}
    try:
        hl = _num(ho["current"]["pointSpread"]["american"])
        al = _num(ao["current"]["pointSpread"]["american"])
        hp, ap = _am(ho["current"]["spread"]), _am(ao["current"]["spread"])
        if None not in (hl, al, hp, ap):
            g["spread"] = {"home_line": hl, "away_line": al, "home_price": hp, "away_price": ap,
                           "open_home_line": _num(((ho.get("open") or {}).get("pointSpread") or {}).get("american"))}
    except Exception:
        pass
    ou, ov, un = _num(d.get("overUnder")), _am(d.get("overOdds")), _am(d.get("underOdds"))
    if ou is not None and ov is not None and un is not None:
        o = d.get("open") or {}
        g["total"] = {"line": ou, "over": ov, "under": un,
                      "open_line": _num(((o.get("total") or {}).get("american"))),
                      "open_over": _am(o.get("over")), "open_under": _am(o.get("under"))}
    ev["game"] = g or None
    return ev["game"]


def _ref_id(ref, marker):
    try:
        return ref.split(marker)[-1].split("?")[0].split("/")[0]
    except Exception:
        return ""


def load_props(ev):
    """Normalised props: list of dicts
       {type, aid, tid, line, am, open_am, shape}   shape in 'pair'|'milestone'|'one'|'ladder'
       For 'pair' there are two entries per (type,id,line): side='over' (first) and side='under'.
    """
    if ev["props_loaded"]:
        return ev["props"]
    ev["props_loaded"] = True
    if not LEAGUES[ev["league"]][3]:
        return None
    base = _event_base(ev) + "/propBets"
    items = []
    d = _get(base, {"limit": 1000, "page": 1})
    if not d:
        return None
    items += d.get("items", [])
    for pg in range(2, min(int(d.get("pageCount", 1) or 1), 4) + 1):
        dd = _get(base, {"limit": 1000, "page": pg})
        if dd:
            items += dd.get("items", [])
    out = []
    groups = {}
    for it in items:
        try:
            tname = it["type"]["name"]
            aid = _ref_id((it.get("athlete") or {}).get("$ref", ""), "/athletes/")
            tid = _ref_id((it.get("team") or {}).get("$ref", ""), "/teams/")
            cur, opn = it.get("current") or {}, it.get("open") or {}
            if "over" in cur:           # soccer schema
                am, oam = _am(cur["over"]), _am(opn.get("over"))
                line = _num((cur.get("target") or {}).get("value"))
                out.append({"type": tname, "aid": aid, "tid": tid, "line": line, "am": am,
                            "open_am": oam, "shape": "ladder"})
                continue
            odds = it.get("odds") or {}
            am, oam = _am((odds.get("american") or {}).get("value")), _am((odds.get("american") or {}).get("open"))
            tot = str((odds.get("total") or {}).get("value", ""))
            tgt = _num((cur.get("target") or {}).get("value"))
            if am is None:
                continue
            if "Milestones" in tname:
                out.append({"type": tname, "aid": aid, "tid": tid, "line": tgt, "am": am,
                            "open_am": oam, "shape": "milestone"})
            elif tgt is not None and not tot.endswith("+"):
                groups.setdefault((tname, aid, tid, tgt), []).append((am, oam))
            else:
                out.append({"type": tname, "aid": aid, "tid": tid, "line": tgt, "am": am,
                            "open_am": oam, "shape": "one"})
        except Exception:
            continue
    for (tname, aid, tid, tgt), lst in groups.items():
        if len(lst) == 2:
            out.append({"type": tname, "aid": aid, "tid": tid, "line": tgt, "am": lst[0][0], "open_am": lst[0][1],
                        "am_other": lst[1][0], "shape": "pair"})
        # a pair group with !=2 items is ambiguous (unlabeled sides) -> dropped
    out = _drop_bad_ladders(ev, out)
    ev["props"] = out
    return out


def _drop_bad_ladders(ev, rows):
    """DraftKings milestone ladders sometimes contain a stray second ladder (duplicate rungs, or a
    rung whose price breaks monotonicity, e.g. 'Rebounds 2+' at +166 next to '3+' at -377).
    A ladder is only trusted if rungs are unique and implied P(X>=n) never rises with n."""
    groups = {}
    for r in rows:
        if r["shape"] == "milestone":
            groups.setdefault((r["type"], r["aid"], r["tid"]), []).append(r)
    bad = set()
    for k, lst in groups.items():
        lst.sort(key=lambda r: r["line"] if r["line"] is not None else -1)
        lines = [r["line"] for r in lst]
        if len(set(lines)) != len(lines):
            bad.add(k)
            continue
        ps = [am_to_prob(r["am"]) for r in lst]
        if any(p is None for p in ps) or any(ps[i + 1] > ps[i] + 0.005 for i in range(len(ps) - 1)):
            bad.add(k)
    ev["ladders_dropped"] = len(bad)
    ev["ladders_total"] = len(groups)
    return [r for r in rows if not (r["shape"] == "milestone" and (r["type"], r["aid"], r["tid"]) in bad)]


def find_event(league, eid):
    return _event_by_id.get((league, str(eid)))


if __name__ == "__main__":
    evs = get_events(days=2, leagues=["NBA", "NHL"])
    print(len(evs), "events;", calls_used(), "calls")
    for e in evs[:3]:
        print(e["league"], e["id"], e["date_et"], e["away"]["abbr"], "@", e["home"]["abbr"], load_game_odds(e))
