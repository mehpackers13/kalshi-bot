# Strategy Lab — 2026-11-13T11:55:24Z

37279 settled markets (37220 with executable candle quotes), 2042 rules tested (group x YES-price bucket x side, taker fees included, entry = first traded hourly candle ask/bid).
Discovery used the oldest 26095 markets; the newest 11184 were held out and never used to pick a rule.

**Rules passing all four gates: 0.** A rule must clear:

1. **economic** — >=30 events, >=+1c/contract, 95% CI above 0, positive in both halves;
2. **adverse selection** — still positive after 1c extra slippage;
3. **multiple comparisons** — Benjamini-Hochberg at q=0.10 over all 2042 rules tested together (cutoff p<=0.02281). Without this, ~1 rule in 20 clears a 95% CI by pure chance, so a larger history yields MORE fake edges, not fewer;
4. **out of sample** — >=10 events in the held-out newest slice and >=+1c there too.

0 rules cleared gates 1, 2 and 4; 0 of those survived the FDR correction. The old VWAP method, with no fees, spread, FDR or holdout, would have passed 7.
A pass is a candidate for forward paper testing, not a proven edge, and never a live bet.

| Rule | Events | Net c | 95% range | Older | Newer | Holdout (n) | p | Gates 1/2/3/4 | Pass |
|---|---|---|---|---|---|---|---|---|---|
| series:KXEREDIVISIE1HTOTAL YES-price 30%-70% buy YES | 5 | +52.2 | [+49.9, +54.5] | None | None | — (0) | 0 | ·YY· |  |
| series:KXLALIGA2BTTS YES-price 30%-70% buy NO | 5 | +50.4 | [+47.9, +52.9] | None | None | — (0) | 0 | ·YY· |  |
| series:KXKLEAGUEBTTS YES-price 30%-70% buy YES | 5 | +42.4 | [+39.8, +45.0] | None | None | — (0) | 0 | ·YY· |  |
| series:KXTFF1LIGBTTS YES-price 30%-70% buy YES | 5 | +40.0 | [+38.0, +42.0] | None | 40.0 | — (0) | 0 | ·YY· |  |
| series:KXTACAPORTSPREAD YES-price 30%-70% buy NO | 6 | +40.9 | [+36.2, +45.6] | None | 40.92 | — (0) | 0 | ·YY· |  |
| series:KXNBLSPREAD YES-price 30%-70% buy NO | 5 | +40.7 | [+34.6, +46.8] | None | None | — (0) | 0 | ·YY· |  |
| series:KXJLEAGUE1HTOTAL YES-price 30%-70% buy NO | 5 | +31.4 | [+29.8, +33.0] | None | None | — (0) | 0 | ·YY· |  |
| series:KXLALIGA2GAME YES-price 10%-30% buy NO | 7 | +23.1 | [+20.3, +25.9] | None | 23.2 | — (0) | 0 | ·YY· |  |
| series:KXAFCCL1HTOTAL YES-price 70%-90% buy YES | 5 | +21.2 | [+18.5, +23.9] | None | None | — (0) | 0 | ·YY· |  |
| family:KXKLEAGUE YES-price 70%-90% buy YES | 5 | +21.6 | [+18.1, +25.1] | None | None | — (0) | 0 | ·YY· |  |
| series:KXNFLMOSTRSHYDS YES-price 70%-90% buy YES | 5 | +22.0 | [+17.9, +26.1] | None | None | — (0) | 0 | ·YY· |  |
| series:KXNHLOT YES-price 10%-30% buy NO | 6 | +18.7 | [+17.7, +19.7] | None | None | +3.7 (7) | 0 | ·YY· |  |
| series:KXLALIGA2TOTAL YES-price 10%-30% buy NO | 5 | +21.8 | [+17.6, +26.0] | None | None | — (0) | 0 | ·YY· |  |
| series:KXEPL2HTOTAL YES-price 10%-30% buy NO | 6 | +19.8 | [+17.4, +22.3] | None | None | — (0) | 0 | ·YY· |  |
| series:KXALLSVENSKANTOTAL YES-price 10%-30% buy NO | 5 | +18.1 | [+16.5, +19.7] | None | None | — (0) | 0 | ·YY· |  |
| series:KXKLEAGUETOTAL YES-price 70%-90% buy YES | 5 | +20.4 | [+16.3, +24.5] | None | None | — (0) | 0 | ·YY· |  |
| series:KXLNBPGAME YES-price 10%-30% buy NO | 5 | +21.0 | [+16.3, +25.7] | None | None | — (0) | 0 | ·YY· |  |
| family:KXLNBP YES-price 10%-30% buy NO | 5 | +21.0 | [+16.3, +25.7] | None | None | — (0) | 0 | ·YY· |  |
| family:KXAFCCL YES-price 70%-90% buy YES | 8 | +19.4 | [+16.1, +22.8] | 19.8 | None | — (0) | 0 | ·YY· |  |
| series:KXARGPREMDIVTOTAL YES-price 10%-30% buy NO | 5 | +16.8 | [+15.8, +17.8] | None | None | — (0) | 0 | ·YY· |  |
| series:KXEPLTOTAL YES-price 70%-90% buy YES | 9 | +18.1 | [+15.7, +20.6] | 20.2 | None | — (0) | 0 | ·YY· |  |
| series:KXBUNDESLIGA1H YES-price 10%-30% buy NO | 6 | +20.3 | [+15.6, +25.1] | None | None | — (0) | 0 | ·YY· |  |
| family:KXELITESERIEN YES-price 70%-90% buy YES | 7 | +19.6 | [+15.5, +23.8] | None | None | — (0) | 0 | ·YY· |  |
| series:KXELITESERIENTOTAL YES-price 70%-90% buy YES | 7 | +20.0 | [+15.4, +24.6] | None | None | — (0) | 0 | ·YY· |  |
| family:KXLOL YES-price 70%-90% buy YES | 11 | +18.0 | [+15.2, +20.8] | 18.0 | None | — (0) | 0 | ·YY· |  |
