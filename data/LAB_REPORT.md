# Strategy Lab — 2026-11-12T03:06:49Z

10877 settled markets (10818 with executable candle quotes), 646 rules tested (group x YES-price bucket x side, taker fees included, entry = first traded hourly candle ask/bid).
Discovery used the oldest 7613 markets; the newest 3264 were held out and never used to pick a rule.

**Rules passing all four gates: 0.** A rule must clear:

1. **economic** — >=30 events, >=+1c/contract, 95% CI above 0, positive in both halves;
2. **adverse selection** — still positive after 1c extra slippage;
3. **multiple comparisons** — Benjamini-Hochberg at q=0.10 over all 646 rules tested together (cutoff p<=0.03083). Without this, ~1 rule in 20 clears a 95% CI by pure chance, so a larger history yields MORE fake edges, not fewer;
4. **out of sample** — >=10 events in the held-out newest slice and >=+1c there too.

0 rules cleared gates 1, 2 and 4; 0 of those survived the FDR correction. The old VWAP method, with no fees, spread, FDR or holdout, would have passed 6.
A pass is a candidate for forward paper testing, not a proven edge, and never a live bet.

| Rule | Events | Net c | 95% range | Older | Newer | Holdout (n) | p | Gates 1/2/3/4 | Pass |
|---|---|---|---|---|---|---|---|---|---|
| series:KXACBGAME YES-price 70%-90% buy YES | 6 | +22.2 | [+17.6, +26.7] | None | None | — (0) | 0 | ·YY· |  |
| series:KXJLEAGUETOTAL YES-price 10%-30% buy NO | 7 | +15.8 | [+14.2, +17.3] | None | None | — (0) | 0 | ·YY· |  |
| series:KXJ2LEAGUETOTAL YES-price 10%-30% buy NO | 7 | +18.1 | [+14.1, +22.1] | None | None | +13.7 (8) | 0 | ·YY· |  |
| series:KXLOLGAME YES-price 70%-90% buy YES | 9 | +16.9 | [+13.9, +19.9] | 16.0 | None | — (0) | 0 | ·YY· |  |
| series:KXLOLGAME YES-price 10%-30% buy NO | 10 | +16.1 | [+13.2, +19.0] | 14.4 | 17.8 | — (0) | 0 | ·YY· |  |
| series:KXK2LEAGUEGAME YES-price 10%-30% buy NO | 5 | +17.0 | [+12.9, +21.1] | None | None | — (0) | 0 | ·YY· |  |
| series:KXNFLTD YES-price 10%-30% buy NO | 5 | +15.2 | [+12.7, +17.7] | None | 15.23 | — (0) | 0 | ·YY· |  |
| series:KXCONMEBOLSUD1HBTTS YES-price 10%-30% buy NO | 8 | +12.4 | [+10.9, +13.8] | 12.14 | None | — (0) | 0 | ·YY· |  |
| series:KXJLEAGUE1HTOTAL YES-price 10%-30% buy NO | 5 | +17.4 | [+9.9, +24.9] | None | None | — (0) | 3e-06 | ·YY· |  |
| series:KXWTIW YES-price 10%-30% buy NO | 5 | +11.0 | [+9.7, +12.3] | None | None | — (0) | 0 | ·YY· |  |
| series:KXNCAAFTEAMTOTAL YES-price 30%-70% buy NO | 15 | +23.9 | [+8.0, +39.7] | 17.54 | 29.43 | +1.1 (8) | 0.0026 | ·YY· |  |
| series:KXVENFUTVETOTAL YES-price 90%-100% buy YES | 8 | +7.8 | [+7.1, +8.4] | None | 8.2 | — (0) | 0 | ·YY· |  |
| series:KXATPCHALLENGERMATCH YES-price 90%-100% buy YES | 5 | +6.0 | [+5.4, +6.6] | None | None | — (0) | 0 | ·YY· |  |
| series:KXLOWTDAL YES-price 30%-70% buy YES | 12 | +28.5 | [+5.0, +52.0] | None | 48.75 | -22.4 (5) | 0.015 | ·YY· |  |
| series:KXJLEAGUETOTAL YES-price 0%-10% buy NO | 6 | +4.5 | [+3.8, +5.2] | None | None | — (0) | 0 | ·YY· |  |
| series:KXITFMATCH YES-price 0%-10% buy NO | 5 | +4.8 | [+3.5, +6.1] | None | None | -34.6 (5) | 4.6e-13 | ·YY· |  |
| series:KXNCAAFOT YES-price 0%-10% buy NO | 6 | +3.7 | [+3.0, +4.3] | None | None | — (0) | 0 | ·YY· |  |
| series:KXFIBAGAME YES-price 0%-10% buy NO | 5 | +4.6 | [+2.8, +6.5] | 4.6 | None | — (0) | 7e-07 | ·YY· |  |
| series:KXNCAAF2H YES-price 0%-10% buy NO | 9 | +3.6 | [+2.7, +4.4] | 3.6 | None | — (0) | 0 | ·YY· |  |
| series:KXFINYLSPREAD YES-price 0%-10% buy NO | 15 | +3.4 | [+2.2, +4.7] | 3.58 | None | — (0) | 2.6e-08 | ·YY· |  |
| series:KXTSAD YES-price 90%-100% buy YES | 5 | +4.2 | [+2.1, +6.3] | None | 4.2 | — (0) | 8.4e-05 | ·YY· |  |
| series:KXRAIN YES-price 90%-100% buy YES | 5 | +4.8 | [+2.0, +7.6] | None | None | — (0) | 0.00057 | ·YY· |  |
| series:KXGOLDD YES-price 0%-10% buy NO | 5 | +3.9 | [+1.9, +5.8] | None | 3.87 | — (0) | 5.4e-05 | ·YY· |  |
| series:KXNCAAFTEAMTOTAL YES-price 70%-90% buy NO | 9 | +31.3 | [+1.9, +60.7] | None | 24.49 | +11.0 (5) | 0.033 | ·Y·· |  |
| series:KXLOWTTTN YES-price 30%-70% buy YES | 20 | +23.0 | [+1.9, +44.0] | 26.91 | 18.13 | — (0) | 0.029 | ·YY· |  |
