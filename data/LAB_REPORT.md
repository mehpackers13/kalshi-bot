# Strategy Lab — 2026-11-17T04:46:20Z

108500 settled markets (108417 with executable candle quotes), 4266 rules tested (group x YES-price bucket x side, taker fees included, entry = first traded hourly candle ask/bid).
Discovery used the oldest 75950 markets; the newest 32550 were held out and never used to pick a rule.

**Rules passing all four gates: 2.** A rule must clear:

1. **economic** — >=30 events, >=+1c/contract, 95% CI above 0, positive in both halves;
2. **adverse selection** — still positive after 1c extra slippage;
3. **multiple comparisons** — Benjamini-Hochberg at q=0.10 over all 4266 rules tested together (cutoff p<=0.02406). Without this, ~1 rule in 20 clears a 95% CI by pure chance, so a larger history yields MORE fake edges, not fewer;
4. **out of sample** — >=10 events in the held-out newest slice and >=+1c there too.

2 rules cleared gates 1, 2 and 4; 2 of those survived the FDR correction. The old VWAP method, with no fees, spread, FDR or holdout, would have passed 24.
A pass is a candidate for forward paper testing, not a proven edge, and never a live bet.

| Rule | Events | Net c | 95% range | Older | Newer | Holdout (n) | p | Gates 1/2/3/4 | Pass |
|---|---|---|---|---|---|---|---|---|---|
| series:KXEREDIVISIE1HTOTAL YES-price 30%-70% buy YES | 5 | +52.2 | [+49.9, +54.5] | None | None | — (0) | 0 | ·YY· |  |
| series:KXKLEAGUEBTTS YES-price 30%-70% buy YES | 5 | +42.4 | [+39.8, +45.0] | None | None | — (0) | 0 | ·YY· |  |
| series:KXTFF1LIGBTTS YES-price 30%-70% buy YES | 6 | +41.0 | [+38.4, +43.6] | None | None | — (0) | 0 | ·YY· |  |
| series:KXTACAPORTSPREAD YES-price 30%-70% buy NO | 6 | +40.9 | [+36.2, +45.6] | 40.92 | None | — (0) | 0 | ·YY· |  |
| series:KXNBAPTSLEADER YES-price 10%-30% buy YES | 14 | +52.9 | [+30.6, +75.1] | None | 56.64 | -14.5 (5) | 2e-06 | ·YY· |  |
| series:KXWNBATOTAL YES-price 10%-30% buy NO | 5 | +23.0 | [+21.9, +24.1] | None | None | — (0) | 0 | ·YY· |  |
| series:KXLIGAMX1HTOTAL YES-price 70%-90% buy YES | 8 | +22.9 | [+21.5, +24.3] | None | 22.2 | — (0) | 0 | ·YY· |  |
| series:KXNFL4QTOTAL YES-price 70%-90% buy YES | 7 | +23.7 | [+20.6, +26.9] | 25.0 | None | — (0) | 0 | ·YY· |  |
| series:KXEFLCUP1HTOTAL YES-price 70%-90% buy YES | 7 | +21.1 | [+18.9, +23.4] | None | 21.14 | — (0) | 0 | ·YY· |  |
| series:KXNBA2D YES-price 70%-90% buy YES | 8 | +22.5 | [+18.6, +26.4] | None | 21.71 | — (0) | 0 | ·YY· |  |
| family:KXKLEAGUE YES-price 70%-90% buy YES | 5 | +21.6 | [+18.1, +25.1] | None | None | — (0) | 0 | ·YY· |  |
| series:KXATPGSPREAD YES-price 70%-90% buy YES | 6 | +20.3 | [+18.0, +22.7] | None | None | — (0) | 0 | ·YY· |  |
| series:KXMLSTEAMTOTAL YES-price 70%-90% buy YES | 5 | +22.2 | [+17.9, +26.5] | None | None | — (0) | 0 | ·YY· |  |
| series:KXEPL2HTOTAL YES-price 10%-30% buy NO | 6 | +19.8 | [+17.4, +22.3] | None | None | — (0) | 0 | ·YY· |  |
| series:KXBSLGAME YES-price 70%-90% buy YES | 5 | +20.2 | [+17.1, +23.3] | None | None | — (0) | 0 | ·YY· |  |
| series:KXMLSTEAMTOTAL YES-price 10%-30% buy NO | 5 | +21.4 | [+17.1, +25.7] | None | None | — (0) | 0 | ·YY· |  |
| family:KXBSL YES-price 70%-90% buy YES | 6 | +19.7 | [+16.9, +22.4] | 18.6 | None | — (0) | 0 | ·YY· |  |
| series:KXALLSVENSKANTOTAL YES-price 10%-30% buy NO | 7 | +18.1 | [+16.8, +19.5] | None | None | — (0) | 0 | ·YY· |  |
| series:KXBTCD YES-price 70%-90% buy YES | 8 | +17.8 | [+16.7, +18.9] | None | 18.37 | -27.7 (5) | 0 | ·YY· |  |
| series:KXKLEAGUETOTAL YES-price 70%-90% buy YES | 5 | +20.4 | [+16.3, +24.5] | None | None | — (0) | 0 | ·YY· |  |
| series:KXBRENTD YES-price 10%-30% buy NO | 7 | +18.4 | [+16.1, +20.8] | None | None | — (0) | 0 | ·YY· |  |
| series:KXEUROLEAGUEGAME YES-price 70%-90% buy YES | 6 | +20.2 | [+16.0, +24.3] | None | None | — (0) | 0 | ·YY· |  |
| family:KXSERIECCUP YES-price 10%-30% buy NO | 6 | +21.5 | [+15.7, +27.3] | None | 21.5 | — (0) | 1.4e-13 | ·YY· |  |
| series:KXEPLTOTAL YES-price 70%-90% buy YES | 9 | +18.1 | [+15.7, +20.6] | 20.2 | None | — (0) | 0 | ·YY· |  |
| series:KXBUNDESLIGA1H YES-price 10%-30% buy NO | 6 | +20.3 | [+15.6, +25.1] | None | None | — (0) | 0 | ·YY· |  |
