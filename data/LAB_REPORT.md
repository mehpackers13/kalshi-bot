# Strategy Lab — 2026-11-20T12:36:48Z

161653 settled markets (161570 with executable candle quotes), 5865 rules tested (group x YES-price bucket x side, taker fees included, entry = first traded hourly candle ask/bid).
Discovery used the oldest 113157 markets; the newest 48496 were held out and never used to pick a rule.

**Rules passing all four gates: 4.** A rule must clear:

1. **economic** — >=30 events, >=+1c/contract, 95% CI above 0, positive in both halves;
2. **adverse selection** — still positive after 1c extra slippage;
3. **multiple comparisons** — Benjamini-Hochberg at q=0.10 over all 5865 rules tested together (cutoff p<=0.02377). Without this, ~1 rule in 20 clears a 95% CI by pure chance, so a larger history yields MORE fake edges, not fewer;
4. **out of sample** — >=10 events in the held-out newest slice and >=+1c there too.

4 rules cleared gates 1, 2 and 4; 4 of those survived the FDR correction. The old VWAP method, with no fees, spread, FDR or holdout, would have passed 49.
A pass is a candidate for forward paper testing, not a proven edge, and never a live bet.

| Rule | Events | Net c | 95% range | Older | Newer | Holdout (n) | p | Gates 1/2/3/4 | Pass |
|---|---|---|---|---|---|---|---|---|---|
| series:KXCFLSPREAD YES-price 30%-70% buy YES | 5 | +49.5 | [+42.5, +56.5] | None | None | — (0) | 0 | ·YY· |  |
| series:KXSVK2LGAME YES-price 10%-30% buy YES | 5 | +54.3 | [+33.1, +75.5] | 54.3 | None | — (0) | 2.8e-07 | ·YY· |  |
| series:KXBUNDESLIGATEAMTOTAL YES-price 10%-30% buy YES | 6 | +52.5 | [+29.8, +75.2] | None | None | — (0) | 3.7e-06 | ·YY· |  |
| series:KXUFCMOF YES-price 70%-90% buy YES | 6 | +27.2 | [+26.4, +28.0] | None | None | — (0) | 0 | ·YY· |  |
| series:KXWNBATOTAL YES-price 10%-30% buy NO | 5 | +23.5 | [+22.4, +24.6] | None | None | — (0) | 0 | ·YY· |  |
| series:KXNFL4QTOTAL YES-price 70%-90% buy YES | 7 | +23.7 | [+20.6, +26.9] | 25.0 | None | — (0) | 0 | ·YY· |  |
| series:KXNCAAFTEAMRECTD YES-price 70%-90% buy YES | 5 | +23.0 | [+19.6, +26.4] | None | None | -35.9 (8) | 0 | ·YY· |  |
| series:KXMLSTEAMTOTAL YES-price 10%-30% buy NO | 10 | +21.8 | [+19.4, +24.1] | 21.71 | None | — (0) | 0 | ·YY· |  |
| series:KXAUTBUNDESTOTAL YES-price 70%-90% buy YES | 7 | +21.0 | [+19.2, +22.8] | None | 20.8 | — (0) | 0 | ·YY· |  |
| family:KXSERIEB YES-price 70%-90% buy YES | 9 | +21.0 | [+19.1, +22.9] | 20.0 | None | — (0) | 0 | ·YY· |  |
| series:KXSERIEBTOTAL YES-price 70%-90% buy YES | 9 | +21.0 | [+19.1, +22.9] | 20.0 | None | — (0) | 0 | ·YY· |  |
| series:KXNBAPTSLEADER YES-price 10%-30% buy YES | 24 | +38.4 | [+19.0, +57.7] | None | 39.87 | -4.7 (5) | 7.3e-05 | ·YY· |  |
| series:KXEFLCUP1HTOTAL YES-price 70%-90% buy YES | 7 | +21.1 | [+18.9, +23.4] | None | 21.14 | — (0) | 0 | ·YY· |  |
| series:KXLIGUE11HBTTS YES-price 10%-30% buy NO | 8 | +20.0 | [+18.5, +21.5] | None | 19.0 | — (0) | 0 | ·YY· |  |
| series:KXLIGUE11H YES-price 10%-30% buy NO | 6 | +22.1 | [+18.2, +25.9] | None | None | — (0) | 0 | ·YY· |  |
| family:KXBSL YES-price 70%-90% buy YES | 7 | +19.6 | [+17.3, +21.9] | 18.67 | None | — (0) | 0 | ·YY· |  |
| series:KXBSLGAME YES-price 70%-90% buy YES | 5 | +20.2 | [+17.1, +23.3] | None | None | — (0) | 0 | ·YY· |  |
| series:KXETTANSPREAD YES-price 10%-30% buy NO | 5 | +19.8 | [+17.0, +22.6] | None | None | — (0) | 0 | ·YY· |  |
| series:KXAUTBSLGAME YES-price 70%-90% buy YES | 5 | +19.8 | [+17.0, +22.6] | 19.8 | None | — (0) | 0 | ·YY· |  |
| family:KXTFF1LIG YES-price 70%-90% buy YES | 7 | +19.9 | [+16.9, +22.8] | None | None | — (0) | 0 | ·YY· |  |
| series:KXTFF1LIGTOTAL YES-price 70%-90% buy YES | 7 | +19.9 | [+16.9, +22.8] | None | None | — (0) | 0 | ·YY· |  |
| series:KXLOWTSAN YES-price 70%-90% buy YES | 5 | +21.2 | [+16.9, +25.5] | None | None | — (0) | 0 | ·YY· |  |
| series:KXROML1TOTAL YES-price 70%-90% buy YES | 6 | +19.5 | [+16.6, +22.4] | None | None | — (0) | 0 | ·YY· |  |
| series:KXLNBELITEGAME YES-price 10%-30% buy NO | 8 | +20.2 | [+16.1, +24.4] | 20.0 | None | — (0) | 0 | ·YY· |  |
| series:KXSUPERLIGTOTAL YES-price 30%-70% buy YES | 9 | +39.3 | [+16.1, +62.6] | None | 37.08 | — (0) | 0.00072 | ·YY· |  |
