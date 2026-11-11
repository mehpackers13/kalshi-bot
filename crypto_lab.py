"""
crypto_lab.py - PAPER-ONLY memecoin lab with a rug screener.

No wallets, no keys, no trading libraries. Free public APIs only:
  DexScreener (universe + prices) and RugCheck (Solana risk summary).
Nothing here can move money. Every "trade" is a row in data/crypto_paper.csv.

Three paper strategies, each paper-buys $100 at priceUsd after costs:
  screened_boosted  - passes the rug screener
  unscreened_control- same universe, NO screener (shows whether the screener adds anything)
  momentum_1h       - passes the screener AND h1 change in [+5%, +40%] AND h1 buys > sells

Cost model (both directions): 1% fee + slippage min(5%, 2*notional/liquidity).
Positions are marked at ~1h/6h/24h (nearest hourly run) and closed at the 24h horizon,
or at -100% ("delisted") if the pair stops returning a price.

Run:  python crypto_lab.py
"""
from __future__ import annotations

import csv
import datetime
import json
import statistics
import time
from pathlib import Path

import requests

try:
    from logger import log
except Exception:  # pragma: no cover - logger is part of the repo, fallback just in case
    def log(message, level="INFO"):
        print("[%s] %s" % (level, message), flush=True)

ROOT = Path(__file__).parent
CSV_PATH = ROOT / "data" / "crypto_paper.csv"
SUMMARY_PATH = ROOT / "data" / "crypto_summary.json"

FIELDS = ["strategy", "chain", "pair", "token", "symbol", "entered_at", "entry_price",
          "liquidity", "fdv", "age_h", "screener", "rug_score", "risks", "mark_1h",
          "mark_6h", "mark_24h", "status", "exit_price", "exited_at", "pnl_pct", "notes"]

STRATEGIES = ["screened_boosted", "unscreened_control", "momentum_1h"]

NOTIONAL = 100.0
FEE = 0.01
MAX_SLIP = 0.05
MAX_NEW_PER_RUN = 15
PER_STRATEGY_CAP = MAX_NEW_PER_RUN // len(STRATEGIES)   # 5 each keeps the arms comparable
REENTRY_DAYS = 7
HORIZON_H = 24.0
MARK_TARGETS = [("mark_1h", 1.0), ("mark_6h", 6.0), ("mark_24h", 24.0)]
RUN_TOLERANCE_H = 0.5          # "nearest run" for hourly cron: due once within 30 min of target

# --- screener thresholds ---------------------------------------------------
MIN_LIQUIDITY = 25_000
MIN_AGE_H = 2.0
MAX_FDV_LIQ = 100.0
HONEYPOT_MIN_BUYS = 50
MAX_RUG_SCORE = 60            # RugCheck score_normalised (higher = riskier)

# Substrings (lowercase) of RugCheck risk names that hard-exclude a token.
# RugCheck names seen/documented: "Freeze Authority still enabled", "Mint Authority still
# enabled", "Low Liquidity", "Copycat token", "Large Amount of LP Unlocked".
BAD_RISK_SUBSTRINGS = [
    "freeze authority",
    "mint authority",
    "low liquidity",
    "copycat",
    "large amount of lp unlocked",
    "creator history of rugged",   # added beyond the spec list: seen live, clearly a rug signal
]

HEADERS = {"User-Agent": "Mozilla/5.0 (paper-research)"}
DEX = "https://api.dexscreener.com"
RUGCHECK = "https://api.rugcheck.xyz/v1/tokens/{}/report/summary"
RUGCHECK_MAX_CALLS = 30       # per run, keeps the job well under its time cap
RUGCHECK_TIMEOUT = 8
RUN_BUDGET_S = 600


def _now():
    return datetime.datetime.utcnow().replace(microsecond=0)


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(s):
    return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ")


def _f(x, default=None):
    try:
        if x is None or x == "":
            return default
        return float(x)
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------
# data fetching
# --------------------------------------------------------------------------
def _get(url, timeout=20, retries=2):
    last = None
    for i in range(retries + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            if r.status_code == 200:
                return r.json()
            last = "HTTP %d" % r.status_code
            if r.status_code == 429:
                time.sleep(3 * (i + 1))
            else:
                time.sleep(1)
        except Exception as e:  # network / json error
            last = str(e)[:80]
            time.sleep(1)
    raise RuntimeError(last or "request failed")


def fetch_candidate_tokens():
    """Return [(chain, token_address)] from DexScreener boosts + profiles (deduped, ordered)."""
    seen, out = set(), []
    for path in ("/token-boosts/latest/v1", "/token-profiles/latest/v1"):
        try:
            data = _get(DEX + path)
        except Exception as e:
            log("crypto_lab: %s failed: %s" % (path, e), "WARN")
            continue
        for row in data if isinstance(data, list) else []:
            chain, addr = row.get("chainId"), row.get("tokenAddress")
            if chain and addr and (chain, addr) not in seen:
                seen.add((chain, addr))
                out.append((chain, addr))
    return out


def fetch_pairs(tokens):
    """Batch-resolve tokens -> pairs. Returns (pairs_by_token, ok_chains).

    pairs_by_token[(chain, token_lower)] = list of raw pair dicts.
    ok_chains = set of (chain, token_lower) whose batch request SUCCEEDED, so a missing token
    in a successful response can be told apart from a failed request.
    """
    by_chain = {}
    for chain, addr in tokens:
        by_chain.setdefault(chain, []).append(addr)
    pairs, answered = {}, set()
    for chain, addrs in by_chain.items():
        for i in range(0, len(addrs), 30):
            chunk = addrs[i:i + 30]
            try:
                data = _get("%s/tokens/v1/%s/%s" % (DEX, chain, ",".join(chunk)))
            except Exception as e:
                log("crypto_lab: tokens batch %s failed: %s" % (chain, e), "WARN")
                continue
            for a in chunk:
                answered.add((chain, a.lower()))
            for p in data if isinstance(data, list) else []:
                tok = ((p.get("baseToken") or {}).get("address") or "").lower()
                pairs.setdefault((p.get("chainId") or chain, tok), []).append(p)
            time.sleep(0.25)
    return pairs, answered


def best_pair(plist):
    """Pick the deepest-liquidity pair for a token that has a usable price."""
    good = [p for p in plist if _f(p.get("priceUsd")) and _f((p.get("liquidity") or {}).get("usd"))]
    if not good:
        return None
    return max(good, key=lambda p: _f((p.get("liquidity") or {}).get("usd"), 0))


def normalize(p, now):
    """Reduce a raw DexScreener pair to the fields we use."""
    liq = _f((p.get("liquidity") or {}).get("usd"), 0.0)
    created = _f(p.get("pairCreatedAt"))
    age_h = (now.replace(tzinfo=datetime.timezone.utc).timestamp() - created / 1000.0) / 3600.0 \
        if created else None
    tx = p.get("txns") or {}
    return {
        "chain": p.get("chainId"),
        "pair": p.get("pairAddress"),
        "token": (p.get("baseToken") or {}).get("address"),
        "symbol": (p.get("baseToken") or {}).get("symbol") or "",
        "price": _f(p.get("priceUsd")),
        "liquidity": liq,
        "fdv": _f(p.get("fdv")),
        "age_h": age_h,
        "vol24": _f((p.get("volume") or {}).get("h24"), 0.0),
        "buys24": int((tx.get("h24") or {}).get("buys") or 0),
        "sells24": int((tx.get("h24") or {}).get("sells") or 0),
        "buys1": int((tx.get("h1") or {}).get("buys") or 0),
        "sells1": int((tx.get("h1") or {}).get("sells") or 0),
        "chg1": _f((p.get("priceChange") or {}).get("h1")),
    }


_rug_calls = [0]


def rugcheck(mint):
    """RugCheck summary for a Solana mint. Returns dict or None when unavailable."""
    if _rug_calls[0] >= RUGCHECK_MAX_CALLS:
        return None
    _rug_calls[0] += 1
    try:
        r = requests.get(RUGCHECK.format(mint), headers=HEADERS, timeout=RUGCHECK_TIMEOUT)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


# --------------------------------------------------------------------------
# screener
# --------------------------------------------------------------------------
def screen(pair, rug):
    """Rug screener. pair = normalize() dict, rug = RugCheck summary dict or None.

    Returns (passed: bool, label: str, reasons: list[str]).
    label: 'full' (Solana, RugCheck consulted), 'partial' (non-Solana, DexScreener checks only),
           'unavailable' (Solana but RugCheck failed -> conservatively rejected).
    """
    reasons = []
    liq = pair.get("liquidity") or 0
    if liq < MIN_LIQUIDITY:
        reasons.append("liquidity<25k")
    age = pair.get("age_h")
    if age is None or age < MIN_AGE_H:
        reasons.append("age<2h")
    fdv = pair.get("fdv")
    if fdv and liq and fdv / liq > MAX_FDV_LIQ:
        reasons.append("fdv/liq>100")
    if pair.get("sells24", 0) == 0 and pair.get("buys24", 0) > HONEYPOT_MIN_BUYS:
        reasons.append("honeypot(no sells)")

    if pair.get("chain") == "solana":
        if rug is None:
            label = "unavailable"
            reasons.append("rugcheck_unavailable")
        else:
            label = "full"
            score = _f(rug.get("score_normalised"), 0)
            if score > MAX_RUG_SCORE:
                reasons.append("rug_score>60")
            for risk in rug.get("risks") or []:
                name = (risk.get("name") or "").lower()
                if any(b in name for b in BAD_RISK_SUBSTRINGS):
                    reasons.append("risk:" + (risk.get("name") or ""))
    else:
        label = "partial"
    return (not reasons), label, reasons


def momentum_ok(pair):
    c = pair.get("chg1")
    return c is not None and 5.0 <= c <= 40.0 and pair.get("buys1", 0) > pair.get("sells1", 0)


# --------------------------------------------------------------------------
# costs and pnl
# --------------------------------------------------------------------------
def slippage(liquidity):
    if not liquidity or liquidity <= 0:
        return MAX_SLIP
    return min(MAX_SLIP, 2.0 * NOTIONAL / liquidity)


def pnl_pct(entry_price, entry_liq, exit_price, exit_liq):
    """Net % return on $100 paper notional after fee+slippage in and out."""
    cost_in = FEE + slippage(entry_liq)
    cost_out = FEE + slippage(exit_liq)
    tokens = NOTIONAL / (entry_price * (1 + cost_in))
    proceeds = tokens * exit_price * (1 - cost_out)
    return (proceeds / NOTIONAL - 1.0) * 100.0


# --------------------------------------------------------------------------
# csv io
# --------------------------------------------------------------------------
def load_rows():
    if not CSV_PATH.exists():
        return []
    with open(CSV_PATH, newline="") as f:
        return list(csv.DictReader(f))


def save_rows(rows):
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CSV_PATH.with_suffix(".tmp")
    with open(tmp, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})
    tmp.replace(CSV_PATH)


# --------------------------------------------------------------------------
# tracking open rows
# --------------------------------------------------------------------------
def update_open(rows, now):
    """Mark/close open rows. Returns (n_marked, n_closed, n_delisted, n_skipped)."""
    open_rows = [r for r in rows if r["status"] == "open"]
    if not open_rows:
        return 0, 0, 0, 0
    tokens = list({(r["chain"], r["token"]) for r in open_rows})
    pairs, answered = fetch_pairs(tokens)
    marked = closed = delisted = skipped = 0
    for r in open_rows:
        key = (r["chain"], r["token"].lower())
        if key not in answered:
            skipped += 1            # API failed for this batch: do not guess, try next run
            continue
        age = (now - _parse(r["entered_at"])).total_seconds() / 3600.0
        cur = None
        for p in pairs.get(key, []):
            if (p.get("pairAddress") or "").lower() == r["pair"].lower() and _f(p.get("priceUsd")):
                cur = p
                break
        entry_price = float(r["entry_price"])
        entry_liq = float(r["liquidity"])
        if cur is None:
            if age >= RUN_TOLERANCE_H:       # grace so a brand-new row is not delisted by a blip
                r["status"] = "delisted"
                r["exit_price"] = "0"
                r["exited_at"] = _iso(now)
                r["pnl_pct"] = "-100.00"
                r["notes"] = (r.get("notes", "") + " price_unavailable").strip()
                delisted += 1
                closed += 1
            continue
        price = _f(cur.get("priceUsd"))
        liq = _f((cur.get("liquidity") or {}).get("usd"), 0.0)
        for field, target in MARK_TARGETS:
            if not r.get(field) and age >= target - RUN_TOLERANCE_H:
                r[field] = repr(price)
                marked += 1
        if age >= HORIZON_H - RUN_TOLERANCE_H:
            r["status"] = "closed"
            r["exit_price"] = repr(price)
            r["exited_at"] = _iso(now)
            r["pnl_pct"] = "%.2f" % pnl_pct(entry_price, entry_liq, price, liq)
            closed += 1
    return marked, closed, delisted, skipped


# --------------------------------------------------------------------------
# summary
# --------------------------------------------------------------------------
def summarize(rows, now):
    out = {"updated": _iso(now), "strategies": {}, "notes": [
        "PAPER ONLY - no money moved, no wallets.",
        "Nothing is 'proven' under 30 closed trades per strategy.",
        "unscreened_control exists to show whether the rug screener adds anything: compare "
        "screened_boosted vs unscreened_control.",
    ]}
    for s in STRATEGIES:
        mine = [r for r in rows if r["strategy"] == s]
        done = [r for r in mine if r["status"] in ("closed", "delisted")]
        pn = [float(r["pnl_pct"]) for r in done if r.get("pnl_pct") not in ("", None)]
        d = {"n_closed": len(pn), "open": sum(1 for r in mine if r["status"] == "open"),
             "n_delisted": sum(1 for r in done if r["status"] == "delisted")}
        if pn:
            mean = statistics.mean(pn)
            se = statistics.stdev(pn) / (len(pn) ** 0.5) if len(pn) > 1 else None
            d.update({
                "win_rate": round(sum(1 for x in pn if x > 0) / len(pn), 4),
                "mean_pnl_pct": round(mean, 2),
                "median_pnl_pct": round(statistics.median(pn), 2),
                "ci95_lo": round(mean - 2 * se, 2) if se is not None else None,
                "ci95_hi": round(mean + 2 * se, 2) if se is not None else None,
                "worst_pnl_pct": round(min(pn), 2),
                "best_pnl_pct": round(max(pn), 2),
            })
        else:
            d.update({"win_rate": None, "mean_pnl_pct": None, "median_pnl_pct": None,
                      "ci95_lo": None, "ci95_hi": None, "worst_pnl_pct": None,
                      "best_pnl_pct": None})
        d["verdict"] = ("inconclusive: %d closed, need 30 before anything is called proven" % len(pn)
                        if len(pn) < 30 else "n>=30: read the CI, not the mean")
        out["strategies"][s] = d
    return out


def write_summary(rows, now):
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SUMMARY_PATH, "w") as f:
        json.dump(summarize(rows, now), f, indent=2)


# --------------------------------------------------------------------------
# main run
# --------------------------------------------------------------------------
def run():
    t0 = time.time()
    now = _now()
    rows = load_rows()
    log("crypto_lab: start, %d existing rows" % len(rows))

    marked, closed, delisted, skipped = update_open(rows, now)
    log("crypto_lab: marks=%d closed=%d delisted=%d skipped=%d" % (marked, closed, delisted, skipped))

    # universe
    cands = fetch_candidate_tokens()
    pairs, _ = fetch_pairs(cands)
    universe = []
    for (chain, addr) in cands:
        p = best_pair(pairs.get((chain, addr.lower()), []))
        if p:
            n = normalize(p, now)
            if n["pair"] and n["token"] and n["price"]:
                universe.append(n)
    log("crypto_lab: universe %d pairs from %d candidate tokens" % (len(universe), len(cands)))

    # 7-day re-entry block per (strategy, pair)
    cutoff = now - datetime.timedelta(days=REENTRY_DAYS)
    blocked = set()
    for r in rows:
        try:
            if _parse(r["entered_at"]) >= cutoff:
                blocked.add((r["strategy"], r["pair"].lower()))
        except Exception:
            blocked.add((r["strategy"], r["pair"].lower()))

    # most liquid first so RugCheck budget is spent on plausible candidates
    universe.sort(key=lambda n: -n["liquidity"])
    taken = {s: 0 for s in STRATEGIES}
    new_rows = []
    rug_cache = {}

    def get_rug(n):
        if n["chain"] != "solana":
            return None
        if n["token"] not in rug_cache:
            rug_cache[n["token"]] = rugcheck(n["token"])
        return rug_cache[n["token"]]

    for n in universe:
        if time.time() - t0 > RUN_BUDGET_S or sum(taken.values()) >= MAX_NEW_PER_RUN:
            break
        want = [s for s in STRATEGIES
                if taken[s] < PER_STRATEGY_CAP and (s, n["pair"].lower()) not in blocked]
        if not want:
            continue
        # Cheap checks first: skip the RugCheck call when the pair can't pass anyway and
        # only the control would take it (control rows still get a rug record below).
        cheap_ok, _, cheap_reasons = screen(dict(n, chain="other"), None)
        need_rug = n["chain"] == "solana" and (cheap_ok or "unscreened_control" in want)
        rug = get_rug(n) if need_rug else None
        passed, label, reasons = screen(n, rug)
        if n["chain"] == "solana" and not need_rug:
            label = "not_checked"
        mom = passed and momentum_ok(n)
        for s in want:
            if s == "screened_boosted" and not passed:
                continue
            if s == "momentum_1h" and not mom:
                continue
            slip = slippage(n["liquidity"])
            risks = ";".join(x.get("name", "") for x in (rug or {}).get("risks") or [])
            note = "slip_in=%.4f would_pass=%s" % (slip, int(passed))
            if not passed:
                note += " reject=" + "|".join(reasons)
            new_rows.append({
                "strategy": s, "chain": n["chain"], "pair": n["pair"], "token": n["token"],
                "symbol": n["symbol"].replace(",", " "), "entered_at": _iso(now),
                "entry_price": repr(n["price"]), "liquidity": "%.0f" % n["liquidity"],
                "fdv": "%.0f" % n["fdv"] if n["fdv"] else "",
                "age_h": "%.1f" % n["age_h"] if n["age_h"] is not None else "",
                "screener": label,
                "rug_score": "" if not rug else rug.get("score_normalised", ""),
                "risks": risks, "mark_1h": "", "mark_6h": "", "mark_24h": "",
                "status": "open", "exit_price": "", "exited_at": "", "pnl_pct": "",
                "notes": note,
            })
            taken[s] += 1
            blocked.add((s, n["pair"].lower()))

    rows.extend(new_rows)
    save_rows(rows)
    write_summary(rows, now)
    log("crypto_lab: new entries %s, rugcheck calls %d, total rows %d, %.1fs" % (
        taken, _rug_calls[0], len(rows), time.time() - t0))
    return {"new": taken, "marked": marked, "closed": closed, "delisted": delisted,
            "universe": len(universe), "seconds": round(time.time() - t0, 1)}


if __name__ == "__main__":
    run()
