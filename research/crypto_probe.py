"""
Read-only probe: how big is the crypto universe, what does the rug screener reject and why,
and which 10 pairs pass. Writes nothing. Run from the repo root: python research/crypto_probe.py
"""
from __future__ import annotations

import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import crypto_lab as cl  # noqa: E402


def main():
    now = cl._now()
    cands = cl.fetch_candidate_tokens()
    pairs, _ = cl.fetch_pairs(cands)
    universe = []
    for chain, addr in cands:
        p = cl.best_pair(pairs.get((chain, addr.lower()), []))
        if p:
            n = cl.normalize(p, now)
            if n["pair"] and n["token"] and n["price"]:
                universe.append(n)
    print("candidate tokens (boosts+profiles): %d" % len(cands))
    print("resolved to usable pairs:           %d" % len(universe))
    print("by chain:", dict(collections.Counter(n["chain"] for n in universe)))

    universe.sort(key=lambda n: -n["liquidity"])
    passed, why = [], collections.Counter()
    rejected = 0
    for n in universe:
        cheap_ok, _, cheap_reasons = cl.screen(dict(n, chain="other"), None)
        rug = None
        if n["chain"] == "solana" and cheap_ok:
            rug = cl.rugcheck(n["token"])      # only spend RugCheck calls on plausible ones
        ok, label, reasons = cl.screen(n, rug) if (cheap_ok or n["chain"] != "solana") \
            else (False, "not_checked", cheap_reasons)
        if ok:
            passed.append((n, label, rug))
        else:
            rejected += 1
            for r in reasons:
                why[r.split(":")[0] if r.startswith("risk:") is False else r] += 1
    print("\nrejected: %d   passed: %d   (rugcheck calls: %d)" % (rejected, len(passed), cl._rug_calls[0]))
    print("rejection reasons (a pair can have several):")
    for k, v in why.most_common():
        print("  %4d  %s" % (v, k))
    print("\nfirst 10 that pass:")
    for n, label, rug in passed[:10]:
        print("  %-10s %-8s liq=$%-9.0f fdv=$%-11s age=%5.1fh h1=%s screener=%s rug=%s" % (
            n["symbol"][:10], n["chain"], n["liquidity"],
            "%.0f" % n["fdv"] if n["fdv"] else "?", n["age_h"] or 0, n["chg1"], label,
            (rug or {}).get("score_normalised", "-")))


if __name__ == "__main__":
    main()
