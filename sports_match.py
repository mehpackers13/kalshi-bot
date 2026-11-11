"""
Strict matcher: parsed Kalshi sports market -> sportsbook (DraftKings via ESPN) reference probability.

Returns None whenever anything is uncertain and counts the reason in STATS / REASONS.

Kalshi sports ticker anatomy (verified live):
    KXNBAGAME-26NOV14DALCLE-DAL          series - yyMONdd + awayCode + homeCode - outcome code
    KXNBASPREAD-26NOV11DENMEM-MEM8       "<Team> wins by over 7.5 points"  (suffix = code + ceil(line))
    KXNBATOTAL-26NOV11DENMEM-257         "Full Game: Over 256.5 points scored"
    KXNBAPTS-26NOV10MILNYK-MILNAMENT15-15  "Nate Ament: 15+ points"  (player code is unusable: use the title)
    KXEPLGAME-26NOV23BREEVE-TIE          "Tie is the result"  (soccer 3-way: home / tie / away markets)
The date segment is the US/Eastern game date; close_time is ~3 days LATER, so a market is only
"live" while the ESPN event state is "pre".

Line equivalences used:
    "N+ points"            == over (N - 0.5) == milestone N+
    "<T> wins by over L"   == T spread -L   (== opponent +L; same devigged number)
    "Over L points"        == total line L, p = devigged over
"""
from __future__ import annotations

import datetime
import re
import unicodedata
from collections import Counter

import sportsbook as sb

try:
    from logger import log
except Exception:  # pragma: no cover
    def log(m, level="INFO"):
        print(m)

# ------------------------------------------------------------------ series table
LEAGUE_PREFIX = {"NBA": "NBA", "NHL": "NHL", "NFL": "NFL", "NCAAF": "NCAAF", "NCAAB": "NCAAMB",
                 "WNBA": "WNBA", "MLB": "MLB", "EPL": "EPL", "LALIGA": "LALIGA",
                 "BUNDESLIGA": "BUNDESLIGA", "SERIEA": "SERIEA", "LIGUE1": "LIGUE1",
                 "UCL": "UCL", "MLS": "MLS", "LIGAMX": "LIGAMX"}
GAME_SUFFIX = {"GAME": "ml", "SPREAD": "spread", "TOTAL": "total", "TEAMTOTAL": "team_total",
               "1HTOTAL": "half_total"}

# prop specs: league -> kalshi suffix -> (label, DK milestone type, DK over/under pair type)
PROPS = {
    "NBA": {"PTS": ("points", "Points Milestones", "Total Points"),
            "REB": ("rebounds", "Rebounds Milestones", "Total Rebounds"),
            "AST": ("assists", "Assists Milestones", "Total Assists"),
            "3PT": ("threes", "3-Point Field Goals Milestones", "Total 3-Point Field Goals"),
            "PRA": ("pra", "Points + Assists + Rebounds Milestones", "Total Points, Rebounds, and Assists")},
    "NHL": {"PTS": ("points", "Points Milestones", "Total Points"),
            "AST": ("assists", "Assists Milestones", "Total Assists"),
            "GOAL": ("goals", "Goals Milestones", None)},
    "NFL": {"RECYDS": ("rec_yds", "Receiving Yards Milestones", "Total Receiving Yards (incl. overtime)"),
            "RSHYDS": ("rush_yds", "Rushing Yards Milestones", "Total Rushing Yards (incl. overtime)"),
            "PASSYDS": ("pass_yds", "Passing Yards Milestones", "Total Passing Yards (incl. overtime)"),
            "PASSTDS": ("pass_td", "Passing Touchdown Milestones", None),
            "TD": ("td", None, None)},
}
PROPS["WNBA"] = {k: v for k, v in PROPS["NBA"].items() if k in ("PTS", "REB", "AST", "3PT")}

# DK one-sided "to score N+" types
TD_TYPES = {1: "Anytime Touchdown Scorer", 2: "Player to score 2 or more touchdowns"}
GOAL_TYPES = {1: "Anytime Goalscorer", 2: "To Score 2+ Goals", 3: "To Score 3+ Goals"}

SERIES = {}   # series ticker -> (league, mtype, spec)
for _lg, _pre in LEAGUE_PREFIX.items():
    for _suf, _mt in GAME_SUFFIX.items():
        SERIES[f"KX{_pre}{_suf}"] = (_lg, _mt, None)
    for _suf, _spec in PROPS.get(_lg, {}).items():
        SERIES[f"KX{_pre}{_suf}"] = (_lg, "prop", _spec)
# soccer anytime goalscorer
for _lg in sb.SOCCER:
    SERIES[f"KX{LEAGUE_PREFIX[_lg]}GOAL"] = (_lg, "prop", ("soccer_goals", None, None))
SERIES["KXNHLGOAL"] = ("NHL", "prop", ("goals", "Goals Milestones", None))

# Kalshi team code -> ESPN abbreviation where they differ (pro leagues; others are learned from the
# GAME/SPREAD markets themselves, see _learn_codes).
ALIASES = {
    "NBA": {"NYK": "NY", "GSW": "GS", "SAS": "SA", "NOP": "NO", "UTA": "UTAH", "WAS": "WSH", "PHX": "PHX"},
    "NHL": {"TBL": "TB", "LAK": "LA", "NJD": "NJ", "SJS": "SJ", "VGK": "VGK", "WAS": "WSH", "UTA": "UTAH",
            "SJ": "SJ", "LA": "LA", "TB": "TB", "NJ": "NJ"},
    "NFL": {"WAS": "WSH", "JAC": "JAX", "LAR": "LAR", "LA": "LAR"},
    "MLB": {"CWS": "CHW", "WSH": "WSH", "AZ": "ARI", "ATH": "ATH", "SF": "SF", "SD": "SD", "TB": "TB"},
}
TEAM_NAME_ALIASES = {"los angeles c": "clippers", "los angeles l": "lakers", "la clippers": "clippers",
                     "los angeles r": "rams", "los angeles ch": "chargers", "la chargers": "chargers",
                     "new york i": "islanders", "new york r": "rangers", "ny islanders": "islanders", "ny rangers": "rangers", "ny knicks": "knicks"}

STATS = Counter()     # "mtype:result" -> count   (result = matched | reason)
REASONS = Counter()   # reason -> count
_learned = {}         # league -> {code: team_id}
_prepared = set()

_MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace("&", " and ").replace("'", "").replace(".", " ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _tnorm(s):
    s = _norm(s)
    s = re.sub(r"\bst\b", "state", s)
    return TEAM_NAME_ALIASES.get(s, s)


_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def norm_player(s: str) -> str:
    toks = [t for t in _norm(s).split() if t not in _SUFFIXES]
    return " ".join(toks)


def parse_ticker(ticker: str):
    """-> (series, date, teamstr, suffix) or None"""
    parts = (ticker or "").split("-")
    if len(parts) < 3:
        return None
    m = re.match(r"^(\d\d)([A-Z]{3})(\d\d)(.+)$", parts[1])
    if not m or m.group(2) not in _MONTHS:
        return None
    try:
        d = datetime.date(2000 + int(m.group(1)), _MONTHS[m.group(2)], int(m.group(3)))
    except ValueError:
        return None
    return parts[0], d, m.group(4), "-".join(parts[2:])


def _count(mtype, reason):
    STATS[f"{mtype}:{reason}"] += 1
    if reason != "matched":
        REASONS[reason] += 1
    return None


# ------------------------------------------------------------------ teams / events
def _team_forms(t):
    f = {_tnorm(t["name"]), _tnorm(t["short"]), _tnorm(t["loc"]), _tnorm(t["nick"]), _tnorm(t["abbr"])}
    f.discard("")
    return f


def _name_matches_team(name, t) -> bool:
    n = _tnorm(name)
    if not n:
        return False
    # exact match against a known name form only; prefix matching is unsafe ("Penn" vs "Penn State")
    return n in _team_forms(t)


def _codes(league, t):
    codes = {t["abbr"].upper()}
    for k, v in ALIASES.get(league, {}).items():
        if v.upper() == t["abbr"].upper():
            codes.add(k)
    for c, tid in _learned.get(league, {}).items():
        if tid == t["id"]:
            codes.add(c)
    return codes


def _dates_around(d):
    return [d, d - datetime.timedelta(days=1), d + datetime.timedelta(days=1)]


def _events_for(league, d):
    out = []
    for dd in _dates_around(d):
        out += sb.get_scoreboard(league, dd)
    seen, uniq = set(), []
    for e in out:
        if e["id"] not in seen:
            seen.add(e["id"])
            uniq.append(e)
    return uniq


def _event_candidates(league, d, teamstr):
    """Events whose team codes spell the ticker's team string (either order)."""
    res = []
    for e in _events_for(league, d):
        ac, hc = _codes(league, e["away"]), _codes(league, e["home"])
        if any(teamstr in (a + h, h + a) for a in ac for h in hc):
            res.append(e)
    return res


def _pick_event(cands, d):
    if not cands:
        return None, "event_not_found"
    exact = [e for e in cands if e["date_et"] == d]
    use = exact or cands
    if len(use) > 1:
        return None, "ambiguous_event"
    return use[0], None


def _parse_team_name(title, subtitle):
    m = re.match(r"^(.+?) wins by over ", title or "") or re.match(r"^(.+?) wins by over ", subtitle or "")
    if m:
        return m.group(1)
    m = re.match(r"^(.+?) wins\??$", title or "") or re.match(r"^(.+?) wins\??$", subtitle or "")
    if m:
        return m.group(1)
    m = re.match(r"^(.+?) (?:over|under) \d", title or "")
    return m.group(1) if m else None


def _learn_codes(markets):
    """Learn Kalshi team code -> ESPN team id from markets that carry both a team name and an
    outcome code (GAME / SPREAD / TEAMTOTAL).  The rest of the team string is the opponent code."""
    for m in markets:
        pt = parse_ticker(m.get("ticker", ""))
        info = SERIES.get(pt[0]) if pt else None
        if not info or info[1] not in ("ml", "spread", "team_total"):
            continue
        league = info[0]
        _, d, S, suf = pt
        if suf.upper() == "TIE":
            continue
        code = re.sub(r"\d+$", "", suf.split("-")[0])
        if not code or not (S.startswith(code) != S.endswith(code)):
            continue
        name = _parse_team_name(m.get("title", ""), m.get("subtitle", ""))
        if not name:
            continue
        other = S[len(code):] if S.startswith(code) else S[:-len(code)]
        hits = []
        for e in _events_for(league, d):
            for t, o in ((e["home"], e["away"]), (e["away"], e["home"])):
                if _name_matches_team(name, t) and not _name_matches_team(name, o):
                    hits.append((e, t, o))
        if len(hits) != 1:
            continue
        e, t, o = hits[0]
        L = _learned.setdefault(league, {})
        if L.get(code, t["id"]) == t["id"] and L.get(other, o["id"]) == o["id"]:
            L[code] = t["id"]
            L[other] = o["id"]
            continue
        # conflicting code -> poison it
        L[code] = "?"
        L[other] = "?"


def prepare(markets, max_days_ahead=8, odds=True, props=True, rosters=True):
    """Pre-fetch scoreboards for every (league, date) the given markets need, then learn team
    codes. Safe to call repeatedly."""
    need = {}
    today = sb.to_eastern_date(datetime.datetime.utcnow())
    for m in markets:
        pt = parse_ticker(m.get("ticker", ""))
        if not pt or pt[0] not in SERIES:
            continue
        if pt[1] < today - datetime.timedelta(days=1) or pt[1] > today + datetime.timedelta(days=max_days_ahead):
            continue
        need.setdefault(SERIES[pt[0]][0], set()).add(pt[1])
    sb.prefetch_scoreboards({(lg, dd) for lg, dates in need.items() for d in dates for dd in _dates_around(d)})
    _learn_codes(markets)
    # parallel warm-up of odds / props, but only for events that actually have Kalshi markets,
    # pro leagues first so the call budget is never spent on college games before them.
    odds_ev, prop_ev = {}, {}
    for m in markets:
        pt = parse_ticker(m.get("ticker", ""))
        info = SERIES.get(pt[0]) if pt else None
        if not info:
            continue
        ev, why = _pick_event(_event_candidates(info[0], pt[1], pt[2]), pt[1])
        if not ev or ev["state"] != "pre":
            continue
        odds_ev[(ev["league"], ev["id"])] = ev
        if info[1] in ("prop", "team_total", "half_total"):
            prop_ev[(ev["league"], ev["id"])] = ev
    order = list(sb.LEAGUES)
    key = lambda e: (order.index(e["league"]), e["start"])
    if odds:
        sb.prefetch_odds(sorted(odds_ev.values(), key=key))
    if props:
        sb.prefetch_props(sorted(prop_ev.values(), key=key))
    pl_ev = {}
    for m in markets:
        pt = parse_ticker(m.get("ticker", ""))
        info = SERIES.get(pt[0]) if pt else None
        if info and info[1] == "prop":
            ev, why = _pick_event(_event_candidates(info[0], pt[1], pt[2]), pt[1])
            if ev and ev["state"] == "pre":
                pl_ev[(ev["league"], ev["id"])] = ev
    if rosters:
        sb.prefetch_rosters(sorted(pl_ev.values(), key=key))
    return {lg: len(ds) for lg, ds in need.items()}


# ------------------------------------------------------------------ the matcher
def _result(p, approx, desc, ev, mtype, **kw):
    r = {"p": max(0.001, min(0.999, p)), "approx": bool(approx), "desc": desc, "event": ev,
         "league": ev["league"], "mtype": mtype, "start": ev["start"]}
    r.update(kw)
    return r


def _check_event_ready(ev, mtype):
    if ev["state"] != "pre":
        return _count(mtype, "event_started")
    return True


def match(m):
    """Parsed Kalshi market -> dict(p=P(YES), approx, desc, event, ...) or None."""
    pt = parse_ticker(m.get("ticker", ""))
    if not pt:
        return _count("other", "bad_ticker")
    series, d, S, suf = pt
    info = SERIES.get(series)
    if not info:
        return _count("other", "series_unsupported")
    league, mtype, spec = info
    try:
        if mtype == "ml":
            return _match_ml(m, league, d, S, suf)
        if mtype == "spread":
            return _match_spread(m, league, d, S, suf)
        if mtype == "total":
            return _match_total(m, league, d, S)
        if mtype == "team_total":
            return _match_team_total(m, league, d, S)
        if mtype == "half_total":
            return _match_half_total(m, league, d, S)
        if mtype == "prop":
            return _match_prop(m, league, d, S, spec)
    except Exception as e:  # never break a scan
        log(f"sports_match error {m.get('ticker')}: {e}", "WARNING")
        return _count(mtype, "exception")
    return _count(mtype, "unhandled")


def _event_for_market(league, mtype, d, S):
    cands = _event_candidates(league, d, S)
    ev, why = _pick_event(cands, d)
    if why:
        return None, _count(mtype, why)
    if _check_event_ready(ev, mtype) is not True:
        return None, None
    return ev, None


def _side_of(ev, name, code_hint=None):
    """home/away for a team name within this event; None if ambiguous."""
    h, a = _name_matches_team(name, ev["home"]), _name_matches_team(name, ev["away"])
    if h and not a:
        return "home"
    if a and not h:
        return "away"
    return None


def _game(ev, mtype):
    g = sb.load_game_odds(ev)
    if g is None:
        _count(mtype, "no_book_odds" if sb.calls_used() < sb.MAX_CALLS else "budget")
    return g


def _match_ml(m, league, d, S, suf):
    ev, _ = _event_for_market(league, "ml", d, S)
    if ev is None:
        return None
    g = _game(ev, "ml")
    if not g:
        return None
    ml = g.get("ml")
    if not ml:
        return _count("ml", "no_book_line")
    three = ml.get("draw") is not None
    if suf.upper() == "TIE":
        if not three:
            return _count("ml", "tie_without_draw_price")
        ph, pd, pa = sb.devig_three(ml["home"], ml["draw"], ml["away"])
        return _result(pd, False, f"DK 3way {ml['home']:+.0f}/{ml['draw']:+.0f}/{ml['away']:+.0f} draw {pd:.3f}", ev, "ml")
    name = _parse_team_name(m.get("title", ""), m.get("subtitle", "")) or m.get("subtitle", "")
    side = _side_of(ev, name)
    code = re.sub(r"\d+$", "", suf)
    if side is None:       # fall back to code
        if code in _codes(league, ev["home"]) and code not in _codes(league, ev["away"]):
            side = "home"
        elif code in _codes(league, ev["away"]) and code not in _codes(league, ev["home"]):
            side = "away"
    if side is None:
        return _count("ml", "team_ambiguous")
    if three:
        ph, pd, pa = sb.devig_three(ml["home"], ml["draw"], ml["away"])
        p = ph if side == "home" else pa
        desc = f"DK 3way {ml['home']:+.0f}/{ml['draw']:+.0f}/{ml['away']:+.0f} {side} {p:.3f}"
    else:
        ph, pa = sb.devig_two(ml["home"], ml["away"])
        p = ph if side == "home" else pa
        desc = f"DK ML {ml['home']:+.0f}/{ml['away']:+.0f} {side} {p:.3f}"
    _count("ml", "matched")
    return _result(p, False, desc, ev, "ml")


def _line_from_title(title, pat):
    mm = re.search(pat, title or "")
    return float(mm.group(1)) if mm else None


def _match_spread(m, league, d, S, suf):
    ev, _ = _event_for_market(league, "spread", d, S)
    if ev is None:
        return None
    L = _line_from_title(m.get("title", "") or m.get("subtitle", ""), r"wins by over (\d+(?:\.\d+)?)")
    name = _parse_team_name(m.get("title", ""), m.get("subtitle", ""))
    if L is None or not name:
        return _count("spread", "title_unparsed")
    side = _side_of(ev, name)
    if side is None:
        return _count("spread", "team_ambiguous")
    g = _game(ev, "spread")
    if not g:
        return None
    sp = g.get("spread")
    if not sp:
        return _count("spread", "no_book_line")
    mine, theirs = (sp["home_line"], sp["away_line"]) if side == "home" else (sp["away_line"], sp["home_line"])
    pm, po = (sp["home_price"], sp["away_price"]) if side == "home" else (sp["away_price"], sp["home_price"])
    if abs(mine - (-L)) < 1e-9:
        p = sb.devig_two(pm, po)[0]
    elif abs(theirs - L) < 1e-9:       # opponent +L  == team does NOT fail to win by over L
        p = sb.devig_two(pm, po)[0]
    else:
        return _count("spread", "line_not_offered")
    _count("spread", "matched")
    return _result(p, False, f"DK spread {side} {mine:+g} {pm:+.0f}/{po:+.0f} -> {p:.3f}", ev, "spread")


def _match_total(m, league, d, S):
    ev, _ = _event_for_market(league, "total", d, S)
    if ev is None:
        return None
    L = _line_from_title(m.get("title", "") or m.get("subtitle", ""), r"[Oo]ver (\d+(?:\.\d+)?)")
    if L is None:
        return _count("total", "title_unparsed")
    g = _game(ev, "total")
    if not g:
        return None
    t = g.get("total")
    if not t:
        return _count("total", "no_book_line")
    if abs(t["line"] - L) > 1e-9:
        return _count("total", "line_not_offered")
    po = sb.devig_two(t["over"], t["under"])[0]
    _count("total", "matched")
    return _result(po, False, f"DK total {t['line']:g} {t['over']:+.0f}/{t['under']:+.0f} over {po:.3f}", ev, "total")


def _match_team_total(m, league, d, S):
    ev, _ = _event_for_market(league, "team_total", d, S)
    if ev is None:
        return None
    L = _line_from_title(m.get("title", "") or "", r"over (\d+(?:\.\d+)?)")
    name = _parse_team_name(m.get("title", ""), m.get("subtitle", ""))
    if L is None or not name:
        return _count("team_total", "title_unparsed")
    side = _side_of(ev, name)
    if side is None:
        return _count("team_total", "team_ambiguous")
    props = sb.load_props(ev)
    if props is None:
        return _count("team_total", "no_book_props" if sb.calls_used() < sb.MAX_CALLS else "budget")
    tid = ev[side]["id"]
    rows = [p for p in props if p["tid"] == tid and p["type"] in ("Team Total Points", "Team Total Goals")
            and p["line"] is not None and abs(p["line"] - L) < 1e-9]
    if not rows:
        return _count("team_total", "line_not_offered")
    if len(rows) > 1:
        return _count("team_total", "book_ambiguous")
    r = rows[0]
    if r["shape"] == "pair":
        p = sb.devig_two(r["am"], r["am_other"])[0]
        approx = True
        desc = f"DK team tot {L:g} {r['am']:+.0f}/{r['am_other']:+.0f} (order-inferred) over {p:.3f}"
    else:
        p, approx = sb.devig_one_sided(r["am"])
        desc = f"DK team tot {L:g} one-sided {r['am']:+.0f} -> {p:.3f}"
    _count("team_total", "matched")
    return _result(p, approx, desc, ev, "team_total")


def _match_half_total(m, league, d, S):
    """Kalshi '1st Half: Over L points' == DK '1st Half Total' pair (unlabeled, first item = over)."""
    ev, _ = _event_for_market(league, "half_total", d, S)
    if ev is None:
        return None
    L = _line_from_title(m.get("title", "") or "", r"[Oo]ver (\d+(?:\.\d+)?)")
    if L is None:
        return _count("half_total", "title_unparsed")
    props = sb.load_props(ev)
    if props is None:
        return _count("half_total", "no_book_props" if sb.calls_used() < sb.MAX_CALLS else "budget")
    rows = [p for p in props if p["type"] == "1st Half Total" and p["shape"] == "pair" and p["line"] is not None
            and abs(p["line"] - L) < 1e-9]
    if len(rows) != 1:
        return _count("half_total", "line_not_offered" if not rows else "book_ambiguous")
    r = rows[0]
    p = sb.devig_two(r["am"], r["am_other"])[0]
    _count("half_total", "matched")
    return _result(p, True, f"DK 1H tot {L:g} {r['am']:+.0f}/{r['am_other']:+.0f} (order-inferred) over {p:.3f}",
                   ev, "half_total")


# ------------------------------------------------------------------ players
def _parse_prop_title(title):
    mm = re.match(r"^(.+?):\s*(\d+(?:\.\d+)?)\+", title or "")
    if not mm:
        return None
    return mm.group(1).strip(), float(mm.group(2))


def resolve_player(m, league=None):
    """Event + athlete resolution for a player prop market (no book fetch).
    -> dict(event, aid, name, threshold, spec, league) or None (reason counted)."""
    pt = parse_ticker(m.get("ticker", ""))
    if not pt:
        return _count("prop", "bad_ticker")
    series, d, S, suf = pt
    info = SERIES.get(series)
    if not info or info[1] != "prop":
        return _count("prop", "series_unsupported")
    lg, _, spec = info
    parsed = _parse_prop_title(m.get("title", "") or m.get("subtitle", ""))
    if not parsed:
        return _count("prop", "title_unparsed")
    pname, thr = parsed
    ev, _ = _event_for_market(lg, "prop", d, S)
    if ev is None:
        return None
    ok = [sb.ensure_roster(lg, ev[side]["id"]) for side in ("home", "away")]
    if not any(ok):
        return _count("prop", "roster_unavailable" if sb.calls_used() < sb.MAX_CALLS else "budget")
    want = norm_player(pname)
    A = sb._load_athletes()["players"]
    cands = [(k.split(":")[1], v["n"]) for k, v in A.items()
             if k.startswith(lg + ":") and v.get("t") in (ev["home"]["id"], ev["away"]["id"])]
    exact = [c for c in cands if norm_player(c[1]) == want]
    if len(exact) == 1:
        aid, nm = exact[0]
    elif len(exact) > 1:
        return _count("prop", "name_ambiguous")
    else:
        toks = want.split()
        if len(toks) < 2:
            return _count("prop", "name_unparsed")
        last, fi = toks[-1], toks[0][0]
        loose = [c for c in cands if norm_player(c[1]).split()[-1:] == [last] and norm_player(c[1])[:1] == fi]
        if len(loose) != 1:
            return _count("prop", "name_not_found" if not loose else "name_ambiguous")
        aid, nm = loose[0]
    return {"event": ev, "aid": aid, "name": nm, "threshold": thr, "spec": spec, "league": lg,
            "side_tid": sb.athlete_team(lg, aid)}


def _match_prop(m, league, d, S, spec):
    rp = resolve_player(m)
    if not rp:
        return None
    ev, aid, thr = rp["event"], rp["aid"], rp["threshold"]
    label, ms_type, pair_type = spec
    props = sb.load_props(ev)
    if props is None:
        return _count("prop", "no_book_props" if sb.calls_used() < sb.MAX_CALLS else "budget")
    mine = [p for p in props if p["aid"] == aid]
    rows = [p for p in mine if ms_type and p["type"] == ms_type and p["shape"] == "milestone"
            and p["line"] is not None and abs(p["line"] - thr) < 1e-9]
    if len(rows) == 1:
        p, approx = sb.devig_one_sided(rows[0]["am"])
        _count("prop", "matched")
        return _result(p, True, f"DK {label} {thr:g}+ {rows[0]['am']:+.0f} one-sided -> {p:.3f}", ev, "prop",
                       player=rp["name"], aid=aid)
    if pair_type:
        rows = [p for p in mine if p["type"] == pair_type and p["shape"] == "pair"
                and p["line"] is not None and abs(p["line"] - (thr - 0.5)) < 1e-9]
        if len(rows) == 1:
            r = rows[0]
            p = sb.devig_two(r["am"], r["am_other"])[0]
            _count("prop", "matched")
            return _result(p, True, f"DK {label} o{thr - 0.5:g} {r['am']:+.0f}/{r['am_other']:+.0f} (order-inferred) -> {p:.3f}",
                           ev, "prop", player=rp["name"], aid=aid)
    os_table = TD_TYPES if label == "td" else (GOAL_TYPES if label in ("goals", "soccer_goals") else {})
    os_type = os_table.get(int(thr)) if float(thr).is_integer() else None
    if os_type:
        rows = [p for p in mine if p["type"] == os_type]
        if len(rows) == 1:
            p, _ = sb.devig_one_sided(rows[0]["am"])
            _count("prop", "matched")
            return _result(p, True, f"DK {os_type} {rows[0]['am']:+.0f} one-sided -> {p:.3f}", ev, "prop",
                           player=rp["name"], aid=aid)
    if not props:
        return _count("prop", "no_book_props")
    if not mine:
        return _count("prop", "player_not_in_book")
    return _count("prop", "line_not_offered")


def fee(p: float) -> float:
    """Kalshi taker fee per contract in dollars: ceil(0.07*P*(1-P)*100)/100."""
    import math
    return math.ceil(round(0.07 * p * (1 - p) * 100, 6)) / 100.0


def summary():
    """{mtype: {'total': n, 'matched': n, 'rate': x, 'reasons': {...}}}"""
    out = {}
    for k, v in STATS.items():
        mt, r = k.split(":", 1)
        o = out.setdefault(mt, {"total": 0, "matched": 0, "reasons": {}})
        o["total"] += v
        if r == "matched":
            o["matched"] += v
        else:
            o["reasons"][r] = v
    for o in out.values():
        o["rate"] = round(o["matched"] / o["total"], 3) if o["total"] else 0.0
    return out
