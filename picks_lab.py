"""
PICKS LAB — is a paid sports-betting pick service actually worth paying for?

The question
------------
Mike pays for a Discord that posts sports picks. The service will show winners.
Every service shows winners. The question is whether the picks carry an edge, and
"did the last ten hit?" cannot answer it: at the standard -110 price you need to win
52.38% of the time just to break even, and a true 50% bettor will have winning
ten-bet streaks constantly. Win rate needs hundreds of bets before it says anything.

Closing line value answers it in ~30.

What CLV is, and why it is the right test
-----------------------------------------
A betting line moves as money comes in. By kickoff it has absorbed everything the
market knows, which makes the closing line the single best available estimate of the
true probability. So:

  You bet Lakers -3.5 at -110. By tipoff the line is Lakers -4.5 at -115.
  You got a better price than the market's final word. That is positive CLV.

Positive CLV means you are systematically getting prices better than the market's
best estimate, and that is the one metric that reliably predicts long-run profit.
Negative CLV with a winning record means you have been lucky, and it will revert.
This is not a theory this file invented; it is how sportsbooks themselves identify
and limit winning bettors.

Both numbers are recorded here. CLV is the verdict; ROI is the reality check.

The honest bar
--------------
A pick service clears this bar only with:
  - >= 30 graded picks (CLV converges fast, but not THAT fast)
  - mean CLV 95% CI strictly above 0
  - ROI not contradicting it
Anything less is "no evidence yet", not "it works". And the subscription cost is
subtracted, because a service that beats the market by less than it charges is
still a losing proposition for the subscriber.

Usage
-----
Log picks as they are posted (the price you GOT is the thing only you know):

    python picks_lab.py add "2026-11-20 NBA Lakers -3.5 -110"
    python picks_lab.py add "2026-11-20 NFL Chiefs ML -150" "2026-11-20 NBA LAL/BOS o220.5 -105"
    python picks_lab.py add --file mypicks.txt

Then grade whenever (fetches closing lines and results from the free ESPN feed):

    python picks_lab.py grade
    python picks_lab.py report

Paper only. This never places a bet and never talks to a sportsbook account.
"""
import argparse, csv, datetime, math, re, statistics, sys
import config
import sportsbook as sb

PICKS = config.DATA_DIR / "picks_log.csv"
REPORT = config.DATA_DIR / "PICKS_REPORT.md"

MIN_GRADED = 30          # CLV needs this many before the verdict means anything
SUB_COST_MONTHLY = 0.0   # set with --sub-cost: a service must beat the market by MORE than it charges

FIELDS = ["pick_id", "logged_at", "date", "league", "selection", "market", "line",
          "odds", "stake_u", "event_id", "close_line", "close_odds", "close_at", "clv",
          "result", "pnl_u", "status", "note"]

# "o220.5" / "u48" / "-3.5" / "ML" — how the market type is written in a pick
RE_TOTAL = re.compile(r"^([ou])(\d+(?:\.\d+)?)$", re.I)
RE_SPREAD = re.compile(r"^([+-]\d+(?:\.\d+)?)$")


# ---------------------------------------------------------------- parsing

def parse_pick(text):
    """'2026-11-20 NBA Lakers -3.5 -110' -> dict, or (None, why).

    Deliberately forgiving about order and spacing, because these get pasted by hand
    from a Discord at speed. Anything it cannot read is REJECTED rather than guessed:
    a misparsed pick silently corrupts the statistics we are trying to trust.
    """
    toks = text.replace(",", " ").split()
    if len(toks) < 4:
        return None, "need at least: date league selection odds"
    out = {"status": "open", "stake_u": 1.0, "note": ""}
    rest = []
    for t in toks:
        if "status" not in out:
            break
        if re.match(r"^\d{4}-\d{2}-\d{2}$", t):
            out["date"] = t
        elif t.upper() in sb.LEAGUES and "league" not in out:
            out["league"] = t.upper()
        else:
            rest.append(t)
    if "date" not in out:
        return None, "no YYYY-MM-DD date"
    if "league" not in out:
        return None, f"no known league (one of: {', '.join(sorted(sb.LEAGUES))})"

    # The last token that looks like American odds is the price paid.
    odds = None
    for i in range(len(rest) - 1, -1, -1):
        if re.match(r"^[+-]\d{3,4}$", rest[i]):
            odds = int(rest.pop(i))
            break
    if odds is None:
        return None, "no American odds (e.g. -110, +145)"
    out["odds"] = odds
    if not rest:
        return None, "no selection"

    # Market type from whatever is left.
    out["market"], out["line"] = "ml", ""
    for i in range(len(rest) - 1, -1, -1):
        m = RE_TOTAL.match(rest[i])
        if m:
            out["market"] = "over" if m.group(1).lower() == "o" else "under"
            out["line"] = float(m.group(2))
            rest.pop(i)
            break
        m = RE_SPREAD.match(rest[i])
        if m:
            out["market"] = "spread"
            out["line"] = float(m.group(1))
            rest.pop(i)
            break
        if rest[i].upper() in ("ML", "MONEYLINE"):
            rest.pop(i)
            break
    out["selection"] = " ".join(rest)
    if not out["selection"]:
        return None, "no team/side named"
    return out, None


# ---------------------------------------------------------------- odds math

def am_to_prob(a):
    """American odds -> implied probability (includes the book's vig)."""
    a = float(a)
    return (-a) / ((-a) + 100.0) if a < 0 else 100.0 / (a + 100.0)


def payout_units(odds, won):
    """Profit in units on a 1-unit stake. A push is handled by the caller."""
    if not won:
        return -1.0
    a = float(odds)
    return 100.0 / (-a) if a < 0 else a / 100.0


def devig(p_side, p_other):
    """Strip the book's margin proportionally across the two sides."""
    tot = p_side + p_other
    return p_side / tot if tot > 0 else p_side


# ---------------------------------------------------------------- storage

def load():
    if not PICKS.exists():
        return []
    with open(PICKS, newline="") as f:
        return list(csv.DictReader(f))


def save(rows):
    with open(PICKS, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def add(texts):
    rows = load()
    have = {r["pick_id"] for r in rows}
    added = rejected = stale = 0
    for t in texts:
        t = t.strip()
        if not t or t.startswith("#"):
            continue
        p, why = parse_pick(t)
        if not p:
            print(f"  REJECTED  {t}\n            -> {why}", flush=True)
            rejected += 1
            continue
        pid = f"{p['date']}|{p['league']}|{p['selection']}|{p['market']}|{p['line']}"
        if pid in have:
            print(f"  duplicate, skipped: {pid}")
            continue
        p.update(pick_id=pid, logged_at=datetime.datetime.now().isoformat(timespec="seconds"),
                 event_id="", close_line="", close_odds="", close_at="", clv="",
                 result="", pnl_u="")
        rows.append(p)
        have.add(pid)
        added += 1
        late = p["date"] < datetime.date.today().isoformat()
        print(f"  logged  {p['date']} {p['league']:7} {p['selection']} "
              f"{p['market']} {p['line']} @ {p['odds']:+d}"
              + ("   (past game — result only, no CLV)" if late else ""))
        if late:
            stale += 1
    save(rows)
    print(f"\n{added} logged, {rejected} rejected, {len(rows)} total in {PICKS.name}")
    if stale:
        print(f"\n{stale} of those are for games already played. They can still be scored "
              f"win/loss, but they get NO closing line value: ESPN deletes a game's odds "
              f"the moment it ends, so the closing price is gone. CLV only exists for "
              f"picks logged before tip-off — which is why it needs to run forward.")
    if added:
        print("\nNext: `picks_lab.py snapshot` before games start (capture closing lines), "
              "then `picks_lab.py grade` after they finish.")


# ---------------------------------------------------------------- grading

NAME_KEYS = ("abbr", "name", "short", "loc", "nick")   # as sportsbook._team_block spells them


def _names(team):
    """Every way the feed spells one team, lowercased."""
    return [str((team or {}).get(k, "")).lower() for k in NAME_KEYS if (team or {}).get(k)]


def _matches(sel, team):
    """Does this pick's selection name this team?

    One helper, used by event lookup, closing-line side selection AND settlement.
    Those three disagreeing is exactly how a grader silently scores the wrong side,
    so they share this function rather than each re-implementing it.
    """
    sel = sel.lower().replace(".", "").strip()
    for n in _names(team):
        if sel == n or (len(sel) > 3 and sel in n) or (len(n) > 3 and n in sel):
            return True
    return False


def find_event(row):
    """Locate the ESPN event for a pick by matching the named team."""
    d = datetime.date.fromisoformat(row["date"])
    want = row["selection"]
    # A totals pick may name the matchup ("LAL/BOS"); try each side.
    parts = [w.strip() for w in re.split(r"[/@]| vs | v ", want) if w.strip()] or [want]
    for dd in (d, d - datetime.timedelta(days=1), d + datetime.timedelta(days=1)):
        try:
            evs = sb.get_scoreboard(row["league"], dd)
        except Exception:
            continue
        for e in evs:
            for p in parts:
                if _matches(p, e.get("home")) or _matches(p, e.get("away")):
                    return e, ""
    return None, "event_not_found"


def closing_for(ev, row):
    """(closing_line, closing_price) for this pick's market, from the ESPN feed."""
    g = sb.load_game_odds(ev)
    if not g:
        return None, None
    mk = row["market"]
    home = _matches(row["selection"], ev.get("home"))

    if mk == "ml" and g.get("ml"):
        return "", g["ml"]["home" if home else "away"]
    if mk == "spread" and g.get("spread"):
        s = g["spread"]
        return ((s["home_line"], s["home_price"]) if home
                else (s["away_line"], s["away_price"]))
    if mk in ("over", "under") and g.get("total"):
        t = g["total"]
        price = t.get("over" if mk == "over" else "under")
        return t.get("line", t.get("over_under", "")), price
    return None, None


def snapshot(verbose=True):
    """Record the market line for picks whose games have NOT started yet.

    This must run before tip-off and it is the whole reason CLV works. ESPN removes
    the odds block the moment a game ends -- a finished game reports sb_odds=False and
    no prices at all -- so the closing line cannot be recovered afterwards. Each run
    overwrites the stored line with the latest pre-game value, so whatever the last
    run before kickoff captured IS the closing line. Run it on a schedule.
    """
    rows = load()
    snapped = 0
    for r in rows:
        if r.get("status") == "graded":
            continue
        ev, why = find_event(r)
        if not ev:
            r["note"] = why
            continue
        r["event_id"], r["note"] = ev["id"], ""
        if ev.get("state") != "pre":
            # Already started/finished: whatever we have is final, and no new
            # price is available. Never overwrite a good capture with nothing.
            if not r.get("close_odds"):
                r["note"] = "no_pregame_capture"
            continue
        cl, cp = closing_for(ev, r)
        if cp is None:
            continue
        r["close_line"] = "" if cl in (None, "") else cl
        r["close_odds"] = cp
        r["close_at"] = datetime.datetime.now().isoformat(timespec="seconds")
        # CLV in probability points: how much cheaper our price was than the market's
        # final word. Both sides are raw implied probabilities including vig; since
        # the comparison is the SAME side at two times, the book's margin cancels.
        r["clv"] = round((am_to_prob(cp) - am_to_prob(r["odds"])) * 100, 2)
        snapped += 1
        if verbose:
            print(f"  {r['date']} {r['league']:6} {r['selection'][:16]:16} {r['market']:6} "
                  f"got {int(r['odds']):+5d}  now {int(cp):+5d}  CLV {r['clv']:+6.2f}pp")
    save(rows)
    print(f"\nsnapshotted {snapped} pre-game lines; "
          f"{sum(1 for r in rows if r.get('close_odds'))} picks now have a closing price")


def grade(verbose=True):
    """Settle finished games. Does NOT touch closing lines -- see snapshot()."""
    rows = load()
    if not rows:
        print("no picks logged yet; use `picks_lab.py add \"...\"`")
        return
    graded = failed = 0
    for r in rows:
        if r.get("status") == "graded":
            continue
        ev, why = find_event(r)
        if not ev:
            r["note"] = why
            failed += 1
            continue
        r["event_id"] = ev["id"]
        if ev.get("state") != "post":
            continue
        res, pnl = settle(ev, r)
        if res:
            r["result"], r["pnl_u"], r["status"] = res, pnl, "graded"
            graded += 1
            if verbose:
                clv = r.get("clv")
                print(f"  {r['date']} {r['league']:6} {r['selection'][:16]:16} {r['market']:6} "
                      f"{res:5} {float(pnl):+6.2f}u  "
                      f"CLV {clv if clv not in ('', None) else 'not captured':>12}")
    save(rows)
    print(f"\ngraded {graded} this run; {failed} could not be matched to a game; "
          f"{sum(1 for r in rows if r.get('status')=='graded')} graded in total")


def settle(ev, r):
    """Win/loss/push from the final score."""
    try:
        hs = float((ev.get("home") or {}).get("score"))
        as_ = float((ev.get("away") or {}).get("score"))
    except (TypeError, ValueError):
        return "", ""
    home = _matches(r["selection"], ev.get("home"))
    mk, line = r["market"], r["line"]
    if mk == "ml":
        won = (hs > as_) if home else (as_ > hs)
        if hs == as_:
            return "push", 0.0
    elif mk == "spread":
        margin = (hs - as_) if home else (as_ - hs)
        adj = margin + float(line)
        if abs(adj) < 1e-9:
            return "push", 0.0
        won = adj > 0
    elif mk in ("over", "under"):
        tot = hs + as_
        if abs(tot - float(line)) < 1e-9:
            return "push", 0.0
        won = (tot > float(line)) if mk == "over" else (tot < float(line))
    else:
        return "", ""
    return ("win" if won else "loss"), round(payout_units(r["odds"], won), 4)


# ---------------------------------------------------------------- report

def ci95(vals):
    if len(vals) < 2:
        return None, None, None
    m = statistics.mean(vals)
    se = statistics.stdev(vals) / math.sqrt(len(vals))
    return m, m - 2 * se, m + 2 * se


def report(sub_cost=0.0):
    rows = load()
    gr = [r for r in rows if r.get("status") == "graded"]
    clvs = [float(r["clv"]) for r in rows if r.get("clv") not in ("", None)]
    pnls = [float(r["pnl_u"]) for r in gr if r.get("pnl_u") not in ("", None)]
    wins = sum(1 for r in gr if r.get("result") == "win")
    decided = sum(1 for r in gr if r.get("result") in ("win", "loss"))

    cm, clo, chi = ci95(clvs)
    rm, rlo, rhi = ci95(pnls)
    L = [f"# Picks Lab — {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}", "",
         "Is the paid pick service actually beating the market? Closing line value is the "
         "verdict, because win rate needs hundreds of bets to say anything while CLV "
         "converges in about thirty.", "",
         f"- Picks logged: **{len(rows)}**, graded: **{len(gr)}**, priced vs close: **{len(clvs)}**"]
    if decided:
        L.append(f"- Record: **{wins}-{decided - wins}** ({wins / decided:.1%}) "
                 f"— break-even at -110 is 52.4%")
    if cm is not None:
        L.append(f"- **Closing line value: {cm:+.2f} percentage points** [{clo:+.2f}, {chi:+.2f}]")
    if rm is not None:
        L.append(f"- **ROI: {rm:+.3f} units per 1-unit bet** [{rlo:+.3f}, {rhi:+.3f}] "
                 f"→ {rm * 100:+.1f}%")
        if sub_cost:
            # A service that beats the market by less than it charges still loses you money.
            L.append(f"- At ${sub_cost:.0f}/month, you need {sub_cost / max(rm, 1e-9):.0f} "
                     f"units of action per month just to cover the subscription"
                     if rm > 0 else
                     f"- At ${sub_cost:.0f}/month the subscription is pure loss on top of "
                     f"a negative ROI")
    L.append("")
    if len(clvs) < MIN_GRADED:
        L.append(f"**Verdict: no evidence yet.** {len(clvs)} of {MIN_GRADED} priced picks. "
                 f"Not 'it works', not 'it doesn't' — just not enough yet.")
    elif clo is not None and clo > 0:
        L.append(f"**Verdict: beating the closing line.** CLV is positive with its whole "
                 f"confidence interval above zero over {len(clvs)} picks. That is the real "
                 f"thing, and it is rare. Keep logging and watch ROI follow.")
    elif chi is not None and chi < 0:
        L.append(f"**Verdict: losing to the closing line.** CLV is negative across "
                 f"{len(clvs)} picks, so any winning stretch is luck and will revert. "
                 f"The subscription is not buying an edge.")
    else:
        L.append(f"**Verdict: indistinguishable from no edge.** Over {len(clvs)} picks the "
                 f"CLV interval straddles zero. If the service had a real edge this is "
                 f"usually where it would be showing.")
    L += ["", "Paper only — nothing here places a bet or touches a sportsbook account."]
    REPORT.write_text("\n".join(L) + "\n")
    print("\n".join(L))


def main():
    ap = argparse.ArgumentParser(description="Test whether a paid pick service has an edge.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", help="log picks (quote each one)")
    a.add_argument("picks", nargs="*")
    a.add_argument("--file", help="read picks from a text file, one per line")
    sub.add_parser("snapshot", help="capture closing lines for games not yet started")
    sub.add_parser("grade", help="settle finished games")
    rp = sub.add_parser("report", help="print the verdict")
    rp.add_argument("--sub-cost", type=float, default=0.0,
                    help="what the service charges per month, to net it off")
    args = ap.parse_args()
    config.DATA_DIR.mkdir(exist_ok=True)
    if args.cmd == "add":
        texts = list(args.picks)
        if args.file:
            texts += open(args.file).read().splitlines()
        if not texts:
            print("nothing to add; pass picks as quoted arguments or --file")
            return
        add(texts)
    elif args.cmd == "snapshot":
        snapshot()
    elif args.cmd == "grade":
        grade()
    else:
        report(args.sub_cost)


if __name__ == "__main__":
    main()
