"""
PAPER LAB — the forward-test engine. Paper only: nothing here places, amends or cancels an order.

Rules live in rules/*.py (each defines NAME, CAP, select(ctx)). Every scan this module:
  1. migrates the legacy data/weather_tail_log.csv into data/paper_log.csv (once; idempotent),
  2. asks each non-killed rule for entries and records them at EXECUTABLE prices
     (YES: pay the ask; NO: pay 1 - yes_bid), fee included,
  3. tracks the quote on open rows (closing line) and settles rows once Kalshi has a result,
  4. summarises per rule (clustered by event), applies kill / candidate gates,
  5. writes data/paper_summary.json and appends status changes to data/paper_events.log.

Promotion to real money is a human decision. "candidate" only means "worth looking at".
"""
import csv
import datetime
import json
import math
import os
import statistics
import time
import collections

import config
from logger import log

LOG = config.DATA_DIR / "paper_log.csv"
STATE = config.DATA_DIR / "paper_rules_state.json"
EVENTS = config.DATA_DIR / "paper_events.log"
SUMMARY = config.DATA_DIR / "paper_summary.json"
LEGACY = config.DATA_DIR / "weather_tail_log.csv"

FIELDS = ["rule", "category", "series", "ticker", "event", "entered_at", "hours_to_close", "yes_bid", "yes_ask",
          "side", "cost", "fee", "model_prob", "volume", "notes", "status", "result", "pnl", "resolved_at",
          "last_yes_bid", "last_yes_ask", "last_seen_at", "close_price", "clv"]

MAX_RESOLVE_CALLS = 150
DEFAULT_CAP = 40
LONGSHOT_KILL_REASON = "forward test -3.9c CI [-7.0,-0.9] over 429 events"

_MARKET_INDEX = {}      # ticker -> parsed market, from the latest run() (used by record_external)


# ───────────────────────────── helpers ─────────────────────────────

def _now_iso() -> str:
    return datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _parse_iso(s: str):
    try:
        return datetime.datetime.fromisoformat(str(s).rstrip("Z"))
    except Exception:
        return None


def _fee(p: float) -> float:
    return math.ceil(round(0.07 * p * (1 - p) * 100, 6)) / 100


def _event(ticker: str) -> str:
    return "-".join(ticker.split("-")[:2])


def _series(ticker: str) -> str:
    return ticker.split("-")[0]


def _f(x, default=None):
    try:
        if x in ("", None):
            return default
        return float(x)
    except Exception:
        return default


def _safe(s, n=120) -> str:
    return str(s or "").replace("\n", " ").replace("\r", " ")[:n]


# ───────────────────────────── storage ─────────────────────────────

def _load_log() -> list:
    if not LOG.exists():
        return []
    with open(LOG, newline="") as f:
        return list(csv.DictReader(f))


def _save_log(rows: list) -> None:
    config.DATA_DIR.mkdir(exist_ok=True)
    tmp = str(LOG) + ".tmp"
    with open(tmp, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})
    os.replace(tmp, LOG)


def _load_state() -> dict:
    try:
        with open(STATE) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    config.DATA_DIR.mkdir(exist_ok=True)
    tmp = str(STATE) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)
    os.replace(tmp, STATE)


def _event_line(msg: str) -> None:
    config.DATA_DIR.mkdir(exist_ok=True)
    with open(EVENTS, "a") as f:
        f.write(f"{_now_iso()} {msg}\n")


def _rule_state(state: dict, rule: str) -> dict:
    s = state.setdefault(rule, {})
    s.setdefault("status", "active")
    s.setdefault("since", _now_iso())
    s.setdefault("reason", "")
    s.setdefault("stats", {})
    return s


# ───────────────────────────── migration ─────────────────────────────

def migrate_legacy(rows: list, state: dict) -> int:
    """Import weather_tail_log.csv rows once (dedupe on rule+ticker). Kills longshot_no_10_30."""
    added = 0
    if LEGACY.exists():
        have = {(r["rule"], r["ticker"]) for r in rows}
        with open(LEGACY, newline="") as f:
            for o in csv.DictReader(f):
                rule = o.get("rule") or "weather_tail"
                t = o.get("ticker", "")
                if not t or (rule, t) in have:
                    continue
                cost = _f(o.get("no_cost"), 0.0)
                rows.append({
                    "rule": rule, "category": o.get("category") or ("Climate and Weather" if t.startswith("KXHIGH") else ""),
                    "series": _series(t), "ticker": t, "event": o.get("event") or _event(t),
                    "entered_at": o.get("entered_at", ""), "hours_to_close": o.get("hours_to_close", ""),
                    "yes_bid": o.get("yes_bid", ""), "yes_ask": o.get("yes_ask", ""), "side": "NO",
                    "cost": o.get("no_cost", ""), "fee": o.get("fee") or (_fee(cost) if cost else ""),
                    "model_prob": "", "volume": "", "notes": "migrated",
                    "status": o.get("status", "open"), "result": o.get("result", ""), "pnl": o.get("pnl", ""),
                    "resolved_at": o.get("resolved_at", ""), "last_yes_bid": "", "last_yes_ask": "",
                    "last_seen_at": "", "close_price": "", "clv": ""})
                have.add((rule, t))
                added += 1
        if added:
            log(f"paper_lab: migrated {added} legacy rows from {LEGACY.name}")
    # longshot is dead whether or not rows were imported now
    ls = state.get("longshot_no_10_30")
    if any(r["rule"] == "longshot_no_10_30" for r in rows) and (not ls or ls.get("status") != "killed"):
        if not (ls and ls.get("killed_by_gate")):
            s = _rule_state(state, "longshot_no_10_30")
            s.update(status="killed", since=_now_iso(), reason=LONGSHOT_KILL_REASON)
            _event_line(f"KILLED longshot_no_10_30: {LONGSHOT_KILL_REASON}")
            log(f"paper_lab: longshot_no_10_30 KILLED ({LONGSHOT_KILL_REASON})")
    return added


# ───────────────────────────── entries ─────────────────────────────

def _price_entry(rule: str, e: dict, m: dict, now_s: str):
    """Turn an entry dict + live market into a CSV row at executable prices, or None."""
    yb, ya = int(m.get("yes_bid") or 0), int(m.get("yes_ask") or 0)
    if yb < 1 or ya > 99 or ya < 1 or (m.get("volume") or 0) < 1:
        return None
    side = str(e.get("side", "")).upper()
    if side == "YES":
        cost = ya / 100.0
    elif side == "NO":
        cost = 1 - yb / 100.0
    else:
        return None
    t = e["ticker"]
    mp = e.get("model_prob")
    return {"rule": rule, "category": e.get("category") or m.get("category") or "",
            "series": e.get("series") or m.get("series") or _series(t), "ticker": t,
            "event": e.get("event") or m.get("event") or _event(t), "entered_at": now_s,
            "hours_to_close": round(float(m.get("hours_to_close") or 0), 1), "yes_bid": yb / 100.0,
            "yes_ask": ya / 100.0, "side": side, "cost": round(cost, 4), "fee": _fee(cost),
            "model_prob": "" if mp is None else round(float(mp), 4), "volume": m.get("volume") or 0,
            "notes": _safe(e.get("notes")), "status": "open", "result": "", "pnl": "", "resolved_at": "",
            "last_yes_bid": yb / 100.0, "last_yes_ask": ya / 100.0, "last_seen_at": now_s,
            "close_price": "", "clv": ""}


def _append_entries(rows: list, rule: str, entries: list, index: dict, cap: int, have: set) -> int:
    now_s = _now_iso()
    added = 0
    for e in entries or []:
        if added >= cap:
            break
        try:
            t = e["ticker"]
            if (rule, t) in have:
                continue
            m = index.get(t)
            if m is None and e.get("yes_bid") is not None:       # external caller supplied prices (cents)
                m = {"yes_bid": e.get("yes_bid"), "yes_ask": e.get("yes_ask"), "volume": e.get("volume", 1),
                     "hours_to_close": e.get("hours_to_close", 0), "category": e.get("category")}
            if m is None:
                continue
            row = _price_entry(rule, e, m, now_s)
            if row:
                rows.append(row)
                have.add((rule, t))
                added += 1
        except Exception as ex:
            log(f"paper_lab: bad entry from {rule}: {ex}", "WARN")
    return added


def record_external(rule: str, entries: list, markets: list = None) -> int:
    """Record entries produced outside rules/ (e.g. the scanner's model edges).

    Prices come from `markets` if given, else from the markets of the latest run(), else from
    yes_bid/yes_ask (cents) / volume / hours_to_close keys on the entry itself.
    Respects a killed status. Returns number recorded."""
    state = _load_state()
    if _rule_state(state, rule)["status"] == "killed":
        return 0
    index = {m["ticker"]: m for m in markets} if markets else _MARKET_INDEX
    rows = _load_log()
    have = {(r["rule"], r["ticker"]) for r in rows}
    n = _append_entries(rows, rule, entries, index, 10 ** 6, have)
    if n:
        _save_log(rows)
    _save_state(state)
    return n


# ───────────────────────────── quotes + resolve ─────────────────────────────

def update_open_quotes(markets: list, rows: list = None) -> int:
    own = rows is None
    if own:
        rows = _load_log()
    idx = {m["ticker"]: m for m in markets}
    now_s = _now_iso()
    n = 0
    for r in rows:
        if r.get("status") != "open":
            continue
        m = idx.get(r["ticker"])
        if m and m.get("yes_ask"):
            r["last_yes_bid"] = int(m.get("yes_bid") or 0) / 100.0
            r["last_yes_ask"] = int(m["yes_ask"]) / 100.0
            r["last_seen_at"] = now_s
            n += 1
    if own and n:
        _save_log(rows)
    return n


def resolve(api, rows: list = None, max_calls: int = MAX_RESOLVE_CALLS) -> int:
    own = rows is None
    if own:
        rows = _load_log()
    now = datetime.datetime.utcnow()
    due = []
    for r in rows:
        if r.get("status") != "open":
            continue
        ent = _parse_iso(r.get("entered_at"))
        if ent is None:
            continue
        if (now - ent).total_seconds() < (_f(r.get("hours_to_close"), 0.0) or 0.0) * 3600:
            continue
        due.append((ent, r))
    due.sort(key=lambda x: x[0])                       # oldest first
    done = calls = 0
    cache = {}
    for _, r in due:
        t = r["ticker"]
        if t not in cache:
            if calls >= max_calls:
                continue
            try:
                cache[t] = api.get_market(t) or {}
            except Exception:
                cache[t] = {}
            calls += 1
            time.sleep(0.1)
        mk = cache[t]
        result = mk.get("result")
        if result not in ("yes", "no"):
            continue
        cost = _f(r.get("cost"), 0.0)
        fee = _f(r.get("fee"))
        if fee is None:
            fee = _fee(cost)
        won = (result == "yes") == (r.get("side") == "YES")
        pnl = ((1 - cost) if won else -cost) - fee
        # Closing line = the last quote we tracked while the market was open. A settled market's own
        # last_price is already the outcome (0.01/0.99), which would make CLV just restate pnl.
        close_price = None
        lb, la = _f(r.get("last_yes_bid")), _f(r.get("last_yes_ask"))
        if lb is not None and la is not None:
            close_price = (lb + la) / 2
        clv = ""
        if close_price is not None:
            clv = round((close_price - cost) if r.get("side") == "YES" else ((1 - close_price) - cost), 4)
        r.update(status="settled", result=result, fee=round(fee, 4), pnl=round(pnl, 4),
                 resolved_at=_now_iso(), close_price="" if close_price is None else round(close_price, 4), clv=clv)
        done += 1
    if own and done:
        _save_log(rows)
    return done


# ───────────────────────────── statistics + gates ─────────────────────────────

def _stats(rows: list) -> dict:
    settled = [r for r in rows if r.get("status") == "settled" and _f(r.get("pnl")) is not None]
    out = {"settled": len(settled), "events": 0, "hit_rate": None, "net": None, "lo": None, "hi": None,
           "clv": None, "open": sum(1 for r in rows if r.get("status") == "open"), "old": None, "new": None}
    if not settled:
        return out
    ev = collections.defaultdict(list)
    first = {}
    for r in settled:
        ev[r["event"]].append(float(r["pnl"]))
        first[r["event"]] = min(first.get(r["event"], "z"), r.get("entered_at") or "z")
    order = sorted(ev, key=lambda e: first[e])
    em = [statistics.mean(ev[e]) for e in order]
    out["events"] = len(em)
    out["net"] = statistics.mean(em)
    if len(em) >= 3:
        se = statistics.stdev(em) / math.sqrt(len(em))
        out["lo"], out["hi"] = out["net"] - 2 * se, out["net"] + 2 * se
    out["hit_rate"] = sum(1 for r in settled if (r["result"] == "yes") == (r.get("side", "NO") == "YES")) / len(settled)
    clvs = [float(r["clv"]) for r in settled if _f(r.get("clv")) is not None]
    if clvs:
        out["clv"] = statistics.mean(clvs)
    if len(em) >= 4:
        h = len(em) // 2
        out["old"], out["new"] = statistics.mean(em[:h]), statistics.mean(em[h:])
    return out


def summarize(rows: list = None) -> str:
    rows = _load_log() if rows is None else rows
    by = collections.defaultdict(list)
    for r in rows:
        by[r["rule"]].append(r)
    state = _load_state()
    parts = []
    for rule in sorted(by):
        s = _stats(by[rule])
        st = state.get(rule, {}).get("status", "active")
        if not s["settled"]:
            parts.append(f"{rule} [{st}]: {s['open']} open, none settled yet")
            continue
        ci = "" if s["lo"] is None else f", 95% CI [{s['lo'] * 100:+.1f}, {s['hi'] * 100:+.1f}]c"
        clv = "" if s["clv"] is None else f", CLV {s['clv'] * 100:+.1f}c"
        parts.append(f"{rule} [{st}]: {s['settled']} settled / {s['events']} events, "
                     f"net {s['net'] * 100:+.1f}c{ci}{clv}; {s['open']} open")
    return " | ".join(parts) if parts else "no paper rows"


def apply_gates(rows: list = None, state: dict = None) -> list:
    """Kill / candidate gates. Returns list of change strings. Persists state if it loaded it."""
    own = state is None
    rows = _load_log() if rows is None else rows
    state = _load_state() if own else state
    by = collections.defaultdict(list)
    for r in rows:
        by[r["rule"]].append(r)
    changes = []
    for rule, rr in by.items():
        s = _stats(rr)
        st = _rule_state(state, rule)
        st["stats"] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in s.items()}
        if st["status"] == "killed":
            continue
        n, mean, lo, hi, clv = s["events"], s["net"], s["lo"], s["hi"], s["clv"]
        new, why = None, ""
        if n >= 30 and hi is not None and hi < 0:
            new, why = "killed", f"{n} events, net {mean * 100:+.1f}c, CI upper {hi * 100:+.1f}c < 0"
        elif n >= 60 and mean < 0 and clv is not None and clv < 0:
            new, why = "killed", f"{n} events, net {mean * 100:+.1f}c and CLV {clv * 100:+.1f}c both negative"
        elif (st["status"] != "candidate" and n >= 30 and mean >= 0.01 and lo is not None and lo > 0
              and s["old"] is not None and s["old"] > 0 and s["new"] > 0):
            new, why = "candidate", (f"{n} events, net {mean * 100:+.1f}c CI [{lo * 100:+.1f},{hi * 100:+.1f}]c, "
                                     f"halves {s['old'] * 100:+.1f}/{s['new'] * 100:+.1f}c")
        if new:
            prev = st["status"]
            st.update(status=new, since=_now_iso(), reason=why)
            if new == "killed":
                st["killed_by_gate"] = True
            msg = f"{new.upper()} {rule}: {why} (was {prev})"
            changes.append(msg)
            _event_line(msg)
            log(f"paper_lab: {msg}")
    if own:
        _save_state(state)
    return changes


def summary_dict(rows: list = None, state: dict = None) -> dict:
    rows = _load_log() if rows is None else rows
    state = _load_state() if state is None else state
    by = collections.defaultdict(list)
    for r in rows:
        by[r["rule"]].append(r)
    out = {}
    c = lambda v: None if v is None else round(v * 100, 2)
    for rule in sorted(set(by) | {k for k in state if not k.startswith("_")}):
        s = _stats(by.get(rule, []))
        st = state.get(rule, {})
        out[rule] = {"status": st.get("status", "active"), "settled": s["settled"], "events": s["events"],
                     "hit_rate": None if s["hit_rate"] is None else round(s["hit_rate"], 4),
                     "net_c": c(s["net"]), "lo_c": c(s["lo"]), "hi_c": c(s["hi"]), "clv_c": c(s["clv"]),
                     "open": s["open"], "old_c": c(s["old"]), "new_c": c(s["new"]),
                     "since": st.get("since", ""), "reason": st.get("reason", "")}
    return out


# ───────────────────────────── main entry ─────────────────────────────

def run(api, markets: list) -> dict:
    t0 = time.time()
    from rules import load_rules
    markets = markets or []
    index = {}
    by_series = collections.defaultdict(list)
    for m in markets:
        m.setdefault("series", _series(m["ticker"]))
        m.setdefault("event", _event(m["ticker"]))
        index[m["ticker"]] = m
        by_series[m["series"]].append(m)
    _MARKET_INDEX.clear()
    _MARKET_INDEX.update(index)

    rows = _load_log()
    state = _load_state()
    migrated = migrate_legacy(rows, state)
    have = {(r["rule"], r["ticker"]) for r in rows}
    now = datetime.datetime.utcnow()
    entered = {}
    for mod in load_rules():
        name = mod.NAME
        st = _rule_state(state, name)
        if st["status"] == "killed":
            continue
        ctx = {"api": api, "markets": markets, "by_series": by_series, "now": now,
               "state": st.setdefault("rule_state", {})}
        n0 = len(markets)
        try:
            entries = mod.select(ctx) or []
            for m in markets[n0:]:                        # a rule fetched extra markets itself
                m.setdefault("series", _series(m["ticker"]))
                index.setdefault(m["ticker"], m)
        except Exception as ex:
            log(f"paper_lab: rule {name} failed: {ex}", "WARN")
            continue
        entered[name] = _append_entries(rows, name, entries, index, getattr(mod, "CAP", DEFAULT_CAP), have)
    quotes = update_open_quotes(markets, rows)
    resolved = resolve(api, rows)
    _save_log(rows)
    changes = apply_gates(rows, state)
    _save_state(state)
    summ = summary_dict(rows, state)
    tmp = str(SUMMARY) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(summ, f, indent=1)
    os.replace(tmp, SUMMARY)
    log(f"paper_lab: {summarize(rows)} (migrated {migrated}, new {entered}, quotes {quotes}, "
        f"resolved {resolved}, {time.time() - t0:.0f}s)")
    return {"migrated": migrated, "entered": entered, "quotes": quotes, "resolved": resolved,
            "changes": changes, "seconds": round(time.time() - t0, 1)}
