# Strategy Lab — 2026-11-23T02:37:36Z

215468 settled markets (215359 with executable candle quotes), 6517 rules tested (group x YES-price bucket x side, taker fees included, entry = first traded hourly candle ask/bid).
Discovery used the oldest 150827 markets; the newest 64641 were held out and never used to pick a rule.

**Rules passing all four gates: 7.** A rule must clear:

1. **economic** — >=30 events, >=+1c/contract, 95% CI above 0, positive in both halves;
2. **adverse selection** — still positive after 1c extra slippage;
3. **multiple comparisons** — Benjamini-Hochberg at q=0.10 over all 6517 rules tested together (cutoff p<=0.02570). Without this, ~1 rule in 20 clears a 95% CI by pure chance, so a larger history yields MORE fake edges, not fewer;
4. **out of sample** — >=10 events in the held-out newest slice and >=+1c there too.

7 rules cleared gates 1, 2 and 4; 7 of those survived the FDR correction. The old VWAP method, with no fees, spread, FDR or holdout, would have passed 78.
A pass is a candidate for forward paper testing, not a proven edge, and never a live bet.

| Rule | Events | Net c | 95% range | Older | Newer | Holdout (n) | p | Gates 1/2/3/4 | Pass |
|---|---|---|---|---|---|---|---|---|---|
| series:KXMIDTERMMOV YES-price 30%-70% buy NO | 8 | +40.7 | [+34.9, +46.5] | None | 40.7 | — (0) | 0 | ·YY· |  |
| series:KXBUNDESLIGATEAMTOTAL YES-price 10%-30% buy YES | 6 | +52.5 | [+29.8, +75.2] | None | None | — (0) | 3.7e-06 | ·YY· |  |
| series:KXNCAAF1HFT YES-price 30%-70% buy NO | 5 | +39.8 | [+27.5, +52.1] | None | None | — (0) | 9.8e-11 | ·YY· |  |
| family:KXNPB YES-price 70%-90% buy YES | 5 | +24.3 | [+22.6, +26.0] | None | None | — (0) | 0 | ·YY· |  |
| series:KXFIFAWGAME YES-price 30%-70% buy YES | 5 | +35.3 | [+21.5, +49.1] | 35.3 | None | — (0) | 3e-07 | ·YY· |  |
| series:KXNFL4QTOTAL YES-price 70%-90% buy YES | 7 | +23.7 | [+20.6, +26.9] | 25.0 | None | — (0) | 0 | ·YY· |  |
| series:KXELHGAME YES-price 70%-90% buy YES | 5 | +24.2 | [+20.0, +28.4] | None | None | — (0) | 0 | ·YY· |  |
| series:KXAUTBUNDESTOTAL YES-price 70%-90% buy YES | 7 | +21.0 | [+19.2, +22.8] | None | 20.8 | — (0) | 0 | ·YY· |  |
| family:KXSERIEB YES-price 70%-90% buy YES | 9 | +21.0 | [+19.1, +22.9] | 20.0 | None | — (0) | 0 | ·YY· |  |
| series:KXSERIEBTOTAL YES-price 70%-90% buy YES | 9 | +21.0 | [+19.1, +22.9] | 20.0 | None | — (0) | 0 | ·YY· |  |
| series:KXAUTBUNDESGAME YES-price 70%-90% buy YES | 6 | +22.7 | [+19.1, +26.3] | None | None | — (0) | 0 | ·YY· |  |
| series:KXEFLCUP1HTOTAL YES-price 70%-90% buy YES | 7 | +21.1 | [+18.9, +23.4] | None | 21.14 | — (0) | 0 | ·YY· |  |
| series:KXBSLGAME YES-price 70%-90% buy YES | 7 | +21.3 | [+18.6, +24.0] | 20.67 | None | +1.7 (6) | 0 | ·YY· |  |
| series:KXLIGUE11HBTTS YES-price 10%-30% buy NO | 8 | +20.0 | [+18.5, +21.5] | None | 19.0 | — (0) | 0 | ·YY· |  |
| family:KXBSL YES-price 70%-90% buy YES | 9 | +20.6 | [+18.3, +22.8] | 20.0 | None | -14.1 (6) | 0 | ·YY· |  |
| series:KXLIGUE11H YES-price 10%-30% buy NO | 6 | +22.1 | [+18.2, +25.9] | None | None | — (0) | 0 | ·YY· |  |
| family:KXTWEEDEDIV YES-price 70%-90% buy YES | 5 | +22.4 | [+17.4, +27.4] | None | None | — (0) | 0 | ·YY· |  |
| series:KXAUTBSLGAME YES-price 70%-90% buy YES | 5 | +19.8 | [+17.0, +22.6] | 19.8 | None | — (0) | 0 | ·YY· |  |
| family:KXTFF1LIG YES-price 70%-90% buy YES | 7 | +19.9 | [+16.9, +22.8] | None | 19.4 | — (0) | 0 | ·YY· |  |
| series:KXTFF1LIGTOTAL YES-price 70%-90% buy YES | 7 | +19.9 | [+16.9, +22.8] | None | 19.4 | — (0) | 0 | ·YY· |  |
| series:KXLOWTSAN YES-price 70%-90% buy YES | 5 | +21.2 | [+16.9, +25.5] | None | None | — (0) | 0 | ·YY· |  |
| series:KXROML1TOTAL YES-price 70%-90% buy YES | 6 | +19.5 | [+16.6, +22.4] | None | 20.0 | — (0) | 0 | ·YY· |  |
| series:KXLNBELITEGAME YES-price 10%-30% buy NO | 8 | +20.2 | [+16.1, +24.4] | 20.0 | None | — (0) | 0 | ·YY· |  |
| series:KXAUTBUNDESSPREAD YES-price 10%-30% buy NO | 5 | +16.5 | [+16.1, +16.9] | None | 16.5 | — (0) | 0 | ·YY· |  |
| series:KXCONCACAFNL1HBTTS YES-price 10%-30% buy NO | 6 | +18.0 | [+15.9, +20.1] | 18.0 | None | -0.3 (6) | 0 | ·YY· |  |
