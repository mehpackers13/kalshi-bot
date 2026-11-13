# Strategy Lab — 2026-11-13T02:41:41Z

30536 settled markets (30477 with executable candle quotes), 1727 rules tested (group x YES-price bucket x side, taker fees included, entry = first traded hourly candle ask/bid).
Discovery used the oldest 21375 markets; the newest 9161 were held out and never used to pick a rule.

**Rules passing all four gates: 0.** A rule must clear:

1. **economic** — >=30 events, >=+1c/contract, 95% CI above 0, positive in both halves;
2. **adverse selection** — still positive after 1c extra slippage;
3. **multiple comparisons** — Benjamini-Hochberg at q=0.10 over all 1727 rules tested together (cutoff p<=0.02297). Without this, ~1 rule in 20 clears a 95% CI by pure chance, so a larger history yields MORE fake edges, not fewer;
4. **out of sample** — >=10 events in the held-out newest slice and >=+1c there too.

0 rules cleared gates 1, 2 and 4; 0 of those survived the FDR correction. The old VWAP method, with no fees, spread, FDR or holdout, would have passed 6.
A pass is a candidate for forward paper testing, not a proven edge, and never a live bet.

| Rule | Events | Net c | 95% range | Older | Newer | Holdout (n) | p | Gates 1/2/3/4 | Pass |
|---|---|---|---|---|---|---|---|---|---|
| series:KXEREDIVISIE1HTOTAL YES-price 30%-70% buy YES | 5 | +52.2 | [+49.9, +54.5] | None | None | — (0) | 0 | ·YY· |  |
| series:KXKLEAGUEBTTS YES-price 30%-70% buy YES | 5 | +42.4 | [+39.8, +45.0] | None | None | — (0) | 0 | ·YY· |  |
| series:KXTACAPORTSPREAD YES-price 30%-70% buy NO | 6 | +40.9 | [+36.2, +45.6] | 40.92 | None | — (0) | 0 | ·YY· |  |
| series:KXNBLSPREAD YES-price 30%-70% buy NO | 5 | +40.7 | [+34.6, +46.8] | None | None | — (0) | 0 | ·YY· |  |
| series:KXJLEAGUE1HTOTAL YES-price 30%-70% buy NO | 5 | +31.4 | [+29.8, +33.0] | None | None | — (0) | 0 | ·YY· |  |
| family:KXLALIGA2 YES-price 70%-90% buy YES | 6 | +22.2 | [+21.0, +23.4] | None | None | — (0) | 0 | ·YY· |  |
| series:KXLALIGA2TOTAL YES-price 70%-90% buy YES | 6 | +22.2 | [+21.0, +23.4] | None | None | — (0) | 0 | ·YY· |  |
| series:KXEPLTOTAL YES-price 30%-70% buy NO | 6 | +38.1 | [+20.7, +55.5] | None | None | — (0) | 1.2e-05 | ·YY· |  |
| series:KXLALIGA2GAME YES-price 10%-30% buy NO | 5 | +23.2 | [+20.1, +26.3] | None | None | — (0) | 0 | ·YY· |  |
| family:KXKLEAGUE YES-price 70%-90% buy YES | 5 | +21.6 | [+18.1, +25.1] | None | None | — (0) | 0 | ·YY· |  |
| series:KXNFLMOSTRSHYDS YES-price 70%-90% buy YES | 5 | +20.8 | [+17.9, +23.7] | None | None | — (0) | 0 | ·YY· |  |
| series:KXNHLOT YES-price 10%-30% buy NO | 6 | +18.7 | [+17.7, +19.7] | None | None | +1.0 (6) | 0 | ·YY· |  |
| series:KXEPL2HTOTAL YES-price 10%-30% buy NO | 6 | +19.8 | [+17.4, +22.3] | None | None | — (0) | 0 | ·YY· |  |
| series:KXNFL2HSPREAD YES-price 10%-30% buy NO | 8 | +18.2 | [+16.3, +20.1] | 17.4 | None | — (0) | 0 | ·YY· |  |
| series:KXKLEAGUETOTAL YES-price 70%-90% buy YES | 5 | +20.4 | [+16.3, +24.5] | None | None | — (0) | 0 | ·YY· |  |
| series:KXLNBPGAME YES-price 10%-30% buy NO | 5 | +21.0 | [+16.3, +25.7] | None | None | — (0) | 0 | ·YY· |  |
| family:KXLNBP YES-price 10%-30% buy NO | 5 | +21.0 | [+16.3, +25.7] | None | None | — (0) | 0 | ·YY· |  |
| family:KXEREDIVISIE YES-price 10%-30% buy YES | 7 | +37.4 | [+15.9, +58.9] | None | 37.17 | — (0) | 0.00051 | ·YY· |  |
| series:KXEPLTOTAL YES-price 10%-30% buy NO | 6 | +16.6 | [+15.3, +17.9] | None | None | — (0) | 0 | ·YY· |  |
| series:KXEPLTOTAL YES-price 70%-90% buy YES | 6 | +16.7 | [+14.7, +18.6] | None | None | — (0) | 0 | ·YY· |  |
| series:KXJ2LEAGUETOTAL YES-price 10%-30% buy NO | 7 | +18.1 | [+14.1, +22.1] | None | None | +13.7 (8) | 0 | ·YY· |  |
| series:KXELITESERIENGAME YES-price 10%-30% buy NO | 5 | +18.3 | [+14.0, +22.6] | None | None | — (0) | 0 | ·YY· |  |
| series:KXLOLGAME YES-price 70%-90% buy YES | 9 | +16.9 | [+13.9, +19.9] | 16.0 | None | — (0) | 0 | ·YY· |  |
| family:KXLOL YES-price 70%-90% buy YES | 9 | +16.9 | [+13.9, +19.9] | 16.0 | None | — (0) | 0 | ·YY· |  |
| series:KXNFLRACE YES-price 70%-90% buy YES | 5 | +16.6 | [+13.5, +19.7] | None | None | — (0) | 0 | ·YY· |  |
