"""
MAKER LAB — test the one Kalshi strategy with peer-reviewed evidence behind it.

The finding
-----------
Burgi, Deng & Whelan, "Makers and Takers: The Economics of the Kalshi Prediction Market"
(University College Dublin, January 2026), transaction-level data on 313,972 contracts:

  * Average post-fee return for MAKERS: -9.64%.  For TAKERS: -31.46%.  Difference
    significant "with an extremely high level of significance".
  * Contracts costing 10c or less lose over 60%. Returns rise with price, and contracts
    above 70c show "statistically significant, though small, positive post-fee returns".
  * The headline: "Makers who buy contracts costing 50c and over earn a 2.6% rate of
    return", statistically significant.
  * The favorite-longshot bias holds in every volume quintile (largest in the lowest) and
    in every year 2021-2025, so it is not an artifact of thin markets or one period.

Our bot has been doing the opposite on both counts: it is a pure TAKER (it buys at the
ask and pays the 7% taker fee), and the rule the paper engine auto-killed was buying
LONGSHOTS at 10-30c -- the -60% bucket. That is a coherent explanation for the audited
-37.55u, independent of any individual model being wrong.

What this script tests
----------------------
On the harvested settled-market history, the same contract priced two ways:

  TAKER  buy YES costs yes_ask        buy NO costs 1 - yes_bid     fee 7%
  MAKER  buy YES costs yes_bid        buy NO costs 1 - yes_ask     fee 1.75%

Posting instead of taking crosses the spread in your favour: to buy NO as a maker you
post a NO bid, which displays as a YES ask, so you pay 1 - yes_ask rather than
1 - yes_bid. Same contract, same outcome, cheaper entry and a quarter of the fee.

THE CATCH, AND IT IS A BIG ONE
-----------------------------
A posted order only fills if someone takes it, and it tends to fill exactly when the
market is moving against you. That is adverse selection, and it is why real maker returns
(-9.64% on average in the paper) are far worse than "cross the spread for free" would
suggest. This script CANNOT measure fill probability from settled candles -- it assumes
every posted order fills at the touch, which is strictly optimistic.

So the maker numbers here are an UPPER BOUND, not a forecast. ADVERSE_C charges an
explicit haircut, and a rule has to survive it, plus the same four gates as the main lab
(sample, positivity, FDR across all rules, out-of-sample holdout). Even then the honest
next step is forward paper testing with real resting orders, where fills are observed
rather than assumed.

Nothing here places an order.

    python maker_lab.py                  # analyse the harvested history
    python maker_lab.py --adverse 2.0    # charge 2c of adverse selection instead of 1c
"""
import argparse, collections, datetime, json, math, statistics
import config
import strategy_lab as lab

RESULTS = config.DATA_DIR / "maker_results.json"
REPORT = config.DATA_DIR / "MAKER_REPORT.md"

TAKER_MULT = 0.07
MAKER_MULT = 0.0175      # Kalshi's maker multiplier. It is 0 on most series (maker fees
                         # apply only to a listed subset), so charging it everywhere is
                         # the conservative choice until the live schedule is confirmed.
BUCKETS = [(0.0, 0.10), (0.10, 0.30), (0.30, 0.50), (0.50, 0.70), (0.70, 0.90), (0.90, 1.0)]
MIN_EVENTS = 30
MIN_NET_C = 1.0
FDR_Q = 0.10
HOLDOUT_FRAC = 0.30


def fee(mult, p):
    return math.ceil(mult * p * (1 - p) * 100) / 100


def tradeable(r, max_spread):
    """Reject quotes where 'post at the touch' is not a real trade.

    This gate is the difference between a result and an artifact. In a market quoted
    2c bid / 20c ask, assuming a fill at the bid means buying for 2c something worth
    about 11c, and booking the 9c as edge. Nobody sells you that -- the spread is wide
    precisely because no one will trade there. Without this filter the lab reported
    +18c/contract for buying longshots as a maker, which contradicts the published
    transaction data for this exchange (cheap contracts lose >60%, makers average
    -9.64%). When a simulation disagrees with measured fills, the simulation is wrong."""
    return (r["px_yes_ask"] - r["px_yes_bid"]) <= max_spread


def cost(side, role, r):
    """Entry cost in dollars. Maker posts at the opposite side of the touch."""
    ask, bid = r["px_yes_ask"], r["px_yes_bid"]
    if role == "taker":
        return ask if side == "YES" else 1 - bid
    return bid if side == "YES" else 1 - ask


def pnl(side, role, r, adverse_c=0.0):
    c = cost(side, role, r)
    if c <= 0 or c >= 1:
        return None
    f = fee(TAKER_MULT if role == "taker" else MAKER_MULT, c)
    win = r["yes"] if side == "YES" else 1 - r["yes"]
    return win - c - f - adverse_c / 100.0


def evaluate(rows, side, role, adverse_c=0.0):
    ev = collections.defaultdict(list)
    for tk, r in rows:
        v = pnl(side, role, r, adverse_c)
        if v is not None:
            ev[lab.event_of(tk)].append(v)
    em = [statistics.mean(v) for v in ev.values()]
    if len(em) < 5:
        return None
    m = statistics.mean(em)
    se = statistics.stdev(em) / math.sqrt(len(em))
    if se > 0:
        t = m / se
        p = 2 * (1 - statistics.NormalDist().cdf(abs(t)))
    else:
        t, p = (float("inf") if m > 0 else 0.0), (0.0 if m > 0 else 1.0)
    return {"events": len(em), "trades": sum(len(v) for v in ev.values()),
            "net_c": round(m * 100, 2), "lo_c": round((m - 2 * se) * 100, 2),
            "hi_c": round((m + 2 * se) * 100, 2), "t": round(t, 2), "p": p}


def bh_threshold(pvals, q=FDR_Q):
    m = len(pvals)
    if not m:
        return 0.0
    thr = 0.0
    for i, p in enumerate(sorted(pvals), start=1):
        if p <= q * i / m:
            thr = p
    return thr


def run(adverse_c, max_spread):
    cache = {k: v for k, v in lab.load_cache().items()
             if v.get("px_src") == "candle" and tradeable(v, max_spread)}
    items = sorted(cache.items(), key=lambda kv: kv[1]["close"])
    if len(items) < 200:
        print(f"only {len(items)} executable rows; run history_harvest.py first")
        return
    cut_i = int(len(items) * (1 - HOLDOUT_FRAC))
    cut_ts = items[cut_i][1]["close"]
    insample, holdout = items[:cut_i], items[cut_i:]
    print(f"{len(items)} executable settled markets; discovery on {len(insample)}, "
          f"holdout {len(holdout)} from {datetime.datetime.utcfromtimestamp(cut_ts).date()}")

    # headline replication: every contract, by price bucket, maker vs taker
    print("\nReplication of the paper's Figure 5/6 on our own data")
    print(f"{'entry cost':>12s} {'events':>7s} {'TAKER net':>10s} {'MAKER net':>10s}")
    head = []
    for lo, hi in BUCKETS:
        top = hi + (0.0001 if hi == 1.0 else 0)
        row = {"bucket": f"{lo:.0%}-{min(hi,1):.0%}"}
        for role in ("taker", "maker"):
            sel = []
            for tk, r in insample:
                for side in ("YES", "NO"):
                    c = cost(side, role, r)
                    if lo <= c < top:
                        sel.append((tk, {**r, "_side": side}))
            # evaluate each side separately then pool by event
            ev = collections.defaultdict(list)
            for tk, r in sel:
                v = pnl(r["_side"], role, r)
                if v is not None:
                    ev[lab.event_of(tk)].append(v)
            em = [statistics.mean(v) for v in ev.values()]
            if len(em) >= 5:
                m = statistics.mean(em)
                se = statistics.stdev(em) / math.sqrt(len(em))
                row[role] = {"events": len(em), "net_c": round(m * 100, 2),
                             "lo_c": round((m - 2 * se) * 100, 2),
                             "hi_c": round((m + 2 * se) * 100, 2)}
            else:
                row[role] = None
        head.append(row)
        t_, m_ = row["taker"], row["maker"]
        print(f"{row['bucket']:>12s} {(m_ or t_ or {}).get('events', 0):7d} "
              f"{(t_['net_c'] if t_ else float('nan')):+10.2f} "
              f"{(m_['net_c'] if m_ else float('nan')):+10.2f}")

    # per-group rules, maker side, full gates
    groups = collections.defaultdict(list)
    for tk, r in insample:
        groups[("category", r["cat"])].append((tk, r))
        groups[("series", r["series"])].append((tk, r))
    groups[("category", "ALL")] = insample
    hgroups = collections.defaultdict(list)
    for tk, r in holdout:
        hgroups[("category", r["cat"])].append((tk, r))
        hgroups[("series", r["series"])].append((tk, r))
    hgroups[("category", "ALL")] = holdout

    out = []
    for (kind, name), rows in groups.items():
        for lo, hi in BUCKETS:
            top = hi + (0.0001 if hi == 1.0 else 0)
            for side in ("YES", "NO"):
                sel = [(tk, r) for tk, r in rows if lo <= cost(side, "maker", r) < top]
                e = evaluate(sel, side, "maker", adverse_c)
                if not e:
                    continue
                tk_e = evaluate(sel, side, "taker")
                hsel = [(tk, r) for tk, r in hgroups.get((kind, name), [])
                        if lo <= cost(side, "maker", r) < top]
                h = evaluate(hsel, side, "maker", adverse_c)
                e.update(kind=kind, name=name, bucket=f"{lo:.0%}-{min(hi,1):.0%}",
                         lo=lo, hi=min(hi, 1.0), side=side,
                         taker_c=tk_e["net_c"] if tk_e else None,
                         hold_events=h["events"] if h else 0,
                         hold_c=h["net_c"] if h else None)
                e["gate_n"] = e["events"] >= MIN_EVENTS
                e["gate_pos"] = e["net_c"] >= MIN_NET_C and e["lo_c"] > 0
                e["gate_oos"] = bool(h and h["events"] >= 10 and h["net_c"] >= MIN_NET_C)
                out.append(e)

    thr = bh_threshold([e["p"] for e in out], FDR_Q)
    passed = []
    for e in out:
        e["gate_fdr"] = bool(e["p"] <= thr) if thr > 0 else False
        e["passed"] = bool(e["gate_n"] and e["gate_pos"] and e["gate_oos"] and e["gate_fdr"])
        if e["passed"]:
            passed.append(e)
    out.sort(key=lambda e: -e["lo_c"])

    res = {"generated": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
           "executable_markets": len(items), "insample": len(insample),
           "holdout": len(holdout), "adverse_c": adverse_c, "max_spread": max_spread,
           "maker_mult": MAKER_MULT,
           "fdr_q": FDR_Q, "bh_threshold": round(thr, 6), "rules_tested": len(out),
           "by_price_bucket": head, "passed": passed, "top": out[:25]}
    RESULTS.write_text(json.dumps(res, indent=1))

    lines = [f"# Maker Lab — {res['generated']}", "",
             "Tests the one Kalshi strategy with peer-reviewed evidence behind it: Burgi, Deng & "
             "Whelan (UCD, Jan 2026) find makers average **-9.64%** vs takers **-31.46%** over "
             "313,972 contracts, and that *\"Makers who buy contracts costing 50c and over earn a "
             "2.6% rate of return\"*.", "",
             f"Our bot is a pure taker buying longshots — the -60% bucket — which is a coherent "
             f"explanation for the audited -37.55u on its own.", "",
             f"{len(items)} executable settled markets; discovery on {len(insample)}, "
             f"{len(holdout)} held out. Maker fee charged at {MAKER_MULT} everywhere "
             f"(it is 0 on most series, so this is conservative). "
             f"{adverse_c:.1f}c of adverse selection charged to every maker entry. "
             f"Quotes wider than {max_spread*100:.0f}c are rejected: assuming a fill at the "
             f"touch in a wide market books the spread as edge and is not a real trade.", "",
             "## Replication by entry cost", "",
             "| Entry cost | Events | Taker net | Maker net |", "|---|---|---|---|"]
    for row in head:
        t_, m_ = row["taker"], row["maker"]
        lines.append(f"| {row['bucket']} | {(m_ or t_ or {}).get('events', 0)} | "
                     f"{t_['net_c']:+.2f}c | {m_['net_c']:+.2f}c |" if t_ and m_ else
                     f"| {row['bucket']} | — | — | — |")
    lines += ["", f"## Rules passing every gate: {len(passed)}", "",
              f"Gates: >={MIN_EVENTS} independent events; >=+{MIN_NET_C:.0f}c with the 95% CI "
              f"above 0; still >=+{MIN_NET_C:.0f}c on held-out data; and Benjamini-Hochberg at "
              f"q={FDR_Q:.2f} across all {len(out)} rules (cutoff p<={thr:.5f}).", "",
              "**The maker numbers are an upper bound, not a forecast.** A resting order only "
              "fills when someone takes it, and it fills precisely when the market is moving "
              "against you. Settled candles cannot measure fill probability, so this assumes "
              "every post fills at the touch. Real maker returns in the paper (-9.64%) are far "
              "worse than crossing the spread for free would imply. Any pass needs forward paper "
              "testing with real resting orders, where fills are observed rather than assumed.", "",
              "| Rule | Events | Maker net | 95% range | Taker net | Holdout | p | Pass |",
              "|---|---|---|---|---|---|---|---|"]
    for e in out[:25]:
        hc = f"{e['hold_c']:+.1f} ({e['hold_events']})" if e["hold_c"] is not None else f"— ({e['hold_events']})"
        lines.append(f"| {e['kind']}:{e['name']} cost {e['bucket']} buy {e['side']} | {e['events']} | "
                     f"{e['net_c']:+.2f} | [{e['lo_c']:+.1f}, {e['hi_c']:+.1f}] | "
                     f"{e['taker_c'] if e['taker_c'] is not None else '—'} | {hc} | "
                     f"{e['p']:.2g} | {'YES' if e['passed'] else ''} |")
    REPORT.write_text("\n".join(lines) + "\n")
    print(f"\nrules tested {len(out)}  BH cutoff p<={thr:.5f}  PASSED {len(passed)}")
    for e in out[:10]:
        print(f"  {e['kind']}:{e['name'][:24]:24s} {e['bucket']:>9s} {e['side']:3s} "
              f"ev {e['events']:4d} maker {e['net_c']:+6.2f}c [{e['lo_c']:+.1f},{e['hi_c']:+.1f}] "
              f"taker {e['taker_c']} hold {e['hold_c']}({e['hold_events']}) "
              f"{'PASS' if e['passed'] else ''}")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adverse", type=float, default=1.0,
                    help="cents of adverse selection charged to every maker entry")
    ap.add_argument("--max-spread", type=float, default=0.02,
                    help="reject quotes wider than this; posting at the touch in a wide "
                         "market is not a real trade (see tradeable())")
    a = ap.parse_args()
    run(a.adverse, a.max_spread)


if __name__ == "__main__":
    main()
