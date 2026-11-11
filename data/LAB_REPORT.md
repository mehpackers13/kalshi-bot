# Strategy Lab — 2026-11-11T18:42:51Z

4500 settled markets (4441 with executable candle quotes), 373 rules tested (group x YES-price bucket x side, taker fees included, entry = first traded hourly candle ask/bid).
Discovery used the oldest 3150 markets; the newest 1350 were held out and never used to pick a rule.

**Rules passing all four gates: 0.** A rule must clear:

1. **economic** — >=30 events, >=+1c/contract, 95% CI above 0, positive in both halves;
2. **adverse selection** — still positive after 1c extra slippage;
3. **multiple comparisons** — Benjamini-Hochberg at q=0.10 over all 373 rules tested together (cutoff p<=0.03522). Without this, ~1 rule in 20 clears a 95% CI by pure chance, so a larger history yields MORE fake edges, not fewer;
4. **out of sample** — >=10 events in the held-out newest slice and >=+1c there too.

0 rules cleared gates 1, 2 and 4; 0 of those survived the FDR correction. The old VWAP method, with no fees, spread, FDR or holdout, would have passed 9.
A pass is a candidate for forward paper testing, not a proven edge, and never a live bet.

| Rule | Events | Net c | 95% range | Older | Newer | Holdout (n) | p | Gates 1/2/3/4 | Pass |
|---|---|---|---|---|---|---|---|---|---|
| series:KXHNLGAME YES-price 70%-90% buy YES | 5 | +22.6 | [+18.7, +26.5] | None | None | — (0) | 0 | ·YY· |  |
| series:KXACBGAME YES-price 70%-90% buy YES | 6 | +22.2 | [+17.6, +26.7] | None | None | — (0) | 0 | ·YY· |  |
| series:KXLOLGAME YES-price 70%-90% buy YES | 8 | +16.5 | [+13.2, +19.8] | None | 17.0 | — (0) | 0 | ·YY· |  |
| series:KXLOLGAME YES-price 10%-30% buy NO | 8 | +15.1 | [+11.9, +18.4] | 14.4 | None | — (0) | 0 | ·YY· |  |
| series:KXLOWTDEN YES-price 30%-70% buy YES | 6 | +44.2 | [+11.6, +76.9] | None | None | — (0) | 0.0068 | ·YY· |  |
| series:KXCONMEBOLSUD1HBTTS YES-price 10%-30% buy NO | 8 | +12.4 | [+10.9, +13.8] | 12.5 | None | — (0) | 0 | ·YY· |  |
| series:KXVENFUTVETOTAL YES-price 90%-100% buy YES | 6 | +7.5 | [+6.8, +8.2] | None | None | — (0) | 0 | ·YY· |  |
| series:KXFIBAGAME YES-price 0%-10% buy NO | 5 | +4.6 | [+2.8, +6.5] | 4.6 | None | — (0) | 7e-07 | ·YY· |  |
| series:KXFINYLSPREAD YES-price 0%-10% buy NO | 15 | +3.4 | [+2.2, +4.7] | 3.58 | None | — (0) | 2.6e-08 | ·YY· |  |
| series:KXHNLGAME YES-price 10%-30% buy YES | 12 | +29.3 | [+2.1, +56.6] | 24.27 | None | — (0) | 0.031 | ·YY· |  |
| series:KXLALIGASPREAD YES-price 0%-10% buy NO | 13 | +3.2 | [+1.7, +4.7] | 2.2 | 3.81 | — (0) | 2.1e-05 | ·YY· |  |
| series:KXLOWTDC YES-price 0%-10% buy NO | 12 | +2.9 | [+1.3, +4.6] | 2.13 | 3.5 | — (0) | 0.00032 | ·YY· |  |
| series:KXLOWTAUS YES-price 0%-10% buy NO | 11 | +2.5 | [+1.3, +3.8] | None | 2.89 | -12.4 (6) | 6.6e-05 | ·YY· |  |
| series:KXWTIW YES-price 0%-10% buy NO | 7 | +1.6 | [+1.0, +2.2] | 1.69 | None | — (0) | 5.4e-08 | ·YY· |  |
| series:KXHIGHTOKC YES-price 0%-10% buy NO | 17 | +2.1 | [+0.8, +3.3] | 2.71 | 1.6 | — (0) | 0.00075 | ··Y· |  |
| series:KXHIGHTSFO YES-price 0%-10% buy NO | 12 | +2.0 | [+0.7, +3.3] | 1.6 | 2.29 | — (0) | 0.0024 | ··Y· |  |
| series:KXHIGHTLV YES-price 0%-10% buy NO | 13 | +1.4 | [+0.7, +2.2] | 1.0 | 1.79 | — (0) | 0.00024 | ··Y· |  |
| series:KXK2LEAGUESPREAD YES-price 0%-10% buy NO | 14 | +2.1 | [+0.6, +3.7] | 2.59 | None | — (0) | 0.0067 | ··Y· |  |
| series:KXAAAGASWNJ YES-price 90%-100% buy YES | 7 | +1.6 | [+0.5, +2.7] | None | None | — (0) | 0.0034 | ··Y· |  |
| series:KXAAAGASDAZ YES-price 0%-10% buy NO | 7 | +0.9 | [+0.3, +1.4] | None | 0.88 | — (0) | 0.0012 | ··Y· |  |
| series:KXLOWTDAL YES-price 0%-10% buy NO | 11 | +1.7 | [+0.3, +3.0] | None | 1.7 | +0.7 (6) | 0.015 | ··Y· |  |
| series:KXAAAGASDRI YES-price 0%-10% buy NO | 8 | +0.9 | [+0.2, +1.5] | None | 0.86 | — (0) | 0.0057 | ··Y· |  |
| series:KXNFLTD YES-price 0%-10% buy NO | 5 | +3.0 | [+0.2, +5.8] | None | 3.0 | — (0) | 0.031 | ··Y· |  |
| series:KXAAAGASDAL YES-price 90%-100% buy YES | 6 | +2.2 | [+0.2, +4.1] | None | 2.17 | — (0) | 0.027 | ··Y· |  |
| series:KXHIGHMIA YES-price 0%-10% buy NO | 15 | +1.3 | [+0.2, +2.4] | 1.5 | 1.17 | -13.5 (7) | 0.019 | ··Y· |  |
