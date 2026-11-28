# Strategy Lab — 2026-11-28T08:48:06Z

293552 settled markets (293443 with executable candle quotes), 7486 rules tested (group x YES-price bucket x side, taker fees included, entry = first traded hourly candle ask/bid).
Discovery used the oldest 205486 markets; the newest 88066 were held out and never used to pick a rule.

**Rules passing all four gates: 9.** A rule must clear:

1. **economic** — >=30 events, >=+1c/contract, 95% CI above 0, positive in both halves;
2. **adverse selection** — still positive after 1c extra slippage;
3. **multiple comparisons** — Benjamini-Hochberg at q=0.10 over all 7486 rules tested together (cutoff p<=0.02514). Without this, ~1 rule in 20 clears a 95% CI by pure chance, so a larger history yields MORE fake edges, not fewer;
4. **out of sample** — >=10 events in the held-out newest slice and >=+1c there too.

9 rules cleared gates 1, 2 and 4; 9 of those survived the FDR correction. The old VWAP method, with no fees, spread, FDR or holdout, would have passed 92.
A pass is a candidate for forward paper testing, not a proven edge, and never a live bet.

| Rule | Events | Net c | 95% range | Older | Newer | Holdout (n) | p | Gates 1/2/3/4 | Pass |
|---|---|---|---|---|---|---|---|---|---|
| series:KXMIDTERMMOV YES-price 30%-70% buy NO | 8 | +40.7 | [+34.9, +46.5] | None | 40.7 | — (0) | 0 | ·YY· |  |
| series:KXVLEAGUE1SPREAD YES-price 30%-70% buy NO | 5 | +32.0 | [+29.3, +34.7] | None | None | — (0) | 0 | ·YY· |  |
| series:KXNHLAST YES-price 70%-90% buy YES | 6 | +25.6 | [+24.0, +27.2] | None | 25.2 | — (0) | 0 | ·YY· |  |
| series:KXECULPTOTAL YES-price 70%-90% buy YES | 5 | +24.4 | [+22.2, +26.6] | None | None | — (0) | 0 | ·YY· |  |
| family:KXECULP YES-price 70%-90% buy YES | 5 | +24.4 | [+22.2, +26.6] | None | None | — (0) | 0 | ·YY· |  |
| series:KXWNBA2QTOTAL YES-price 70%-90% buy YES | 5 | +23.6 | [+20.6, +26.6] | 23.6 | None | — (0) | 0 | ·YY· |  |
| series:KXEFLL1GAME YES-price 70%-90% buy YES | 5 | +23.4 | [+20.3, +26.5] | None | None | — (0) | 0 | ·YY· |  |
| series:KXVLEAGUE1TOTAL YES-price 70%-90% buy YES | 6 | +22.3 | [+20.2, +24.4] | None | 22.4 | — (0) | 0 | ·YY· |  |
| series:KXINDSLTOTAL YES-price 30%-70% buy NO | 5 | +37.2 | [+19.4, +55.0] | None | None | — (0) | 2.9e-05 | ·YY· |  |
| series:KXAUTBUNDESTOTAL YES-price 70%-90% buy YES | 7 | +21.0 | [+19.2, +22.8] | None | 20.8 | — (0) | 0 | ·YY· |  |
| series:KXNFL4QTOTAL YES-price 70%-90% buy YES | 11 | +22.0 | [+19.2, +24.8] | 23.67 | None | +15.5 (5) | 0 | ·YY· |  |
| family:KXSERIEB YES-price 70%-90% buy YES | 9 | +21.0 | [+19.1, +22.9] | 20.0 | None | — (0) | 0 | ·YY· |  |
| series:KXSERIEBTOTAL YES-price 70%-90% buy YES | 9 | +21.0 | [+19.1, +22.9] | 20.0 | None | — (0) | 0 | ·YY· |  |
| series:KXAUTBUNDESGAME YES-price 70%-90% buy YES | 6 | +22.7 | [+19.1, +26.3] | None | None | — (0) | 0 | ·YY· |  |
| series:KXEFLCUP1HTOTAL YES-price 70%-90% buy YES | 7 | +21.1 | [+18.9, +23.4] | None | 21.14 | — (0) | 0 | ·YY· |  |
| series:KXSVNPLTOTAL YES-price 10%-30% buy NO | 5 | +22.2 | [+17.9, +26.6] | None | None | — (0) | 0 | ·YY· |  |
| series:KXLOWTSAN YES-price 70%-90% buy YES | 6 | +20.8 | [+17.3, +24.4] | None | None | — (0) | 0 | ·YY· |  |
| series:KXBRASILEIROGAME YES-price 70%-90% buy YES | 5 | +20.0 | [+16.8, +23.2] | None | None | — (0) | 0 | ·YY· |  |
| series:KXBRENTW YES-price 70%-90% buy YES | 8 | +20.1 | [+16.6, +23.5] | 21.3 | None | — (0) | 0 | ·YY· |  |
| series:KXSHLGAME YES-price 10%-30% buy NO | 6 | +20.5 | [+16.6, +24.4] | None | None | — (0) | 0 | ·YY· |  |
| series:KXTACAPORTSPREAD YES-price 30%-70% buy NO | 12 | +33.0 | [+16.5, +49.5] | 33.04 | None | — (0) | 6.3e-05 | ·YY· |  |
| series:KXLNBELITEGAME YES-price 10%-30% buy NO | 8 | +20.2 | [+16.1, +24.4] | 20.0 | None | — (0) | 0 | ·YY· |  |
| series:KXAUTBUNDESSPREAD YES-price 10%-30% buy NO | 5 | +16.5 | [+16.1, +16.9] | None | 16.5 | — (0) | 0 | ·YY· |  |
| series:KXTRUMPSAY YES-price 70%-90% buy YES | 5 | +18.2 | [+15.8, +20.5] | None | None | — (0) | 0 | ·YY· |  |
| series:KXALLSVENSKANTOTAL YES-price 10%-30% buy NO | 12 | +17.3 | [+15.8, +18.8] | 17.5 | 17.17 | — (0) | 0 | ·YY· |  |
