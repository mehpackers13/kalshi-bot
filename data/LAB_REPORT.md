# Strategy Lab — 2026-11-12T00:36:47Z

32169 settled markets (32110 with executable candle quotes), 1331 rules tested (group x YES-price bucket x side, taker fees included, entry = first traded hourly candle ask/bid).
Discovery used the oldest 22518 markets; the newest 9651 were held out and never used to pick a rule.

**Rules passing all four gates: 0.** A rule must clear:

1. **economic** — >=30 events, >=+1c/contract, 95% CI above 0, positive in both halves;
2. **adverse selection** — still positive after 1c extra slippage;
3. **multiple comparisons** — Benjamini-Hochberg at q=0.10 over all 1331 rules tested together (cutoff p<=0.02594). Without this, ~1 rule in 20 clears a 95% CI by pure chance, so a larger history yields MORE fake edges, not fewer;
4. **out of sample** — >=10 events in the held-out newest slice and >=+1c there too.

0 rules cleared gates 1, 2 and 4; 0 of those survived the FDR correction. The old VWAP method, with no fees, spread, FDR or holdout, would have passed 7.
A pass is a candidate for forward paper testing, not a proven edge, and never a live bet.

| Rule | Events | Net c | 95% range | Older | Newer | Holdout (n) | p | Gates 1/2/3/4 | Pass |
|---|---|---|---|---|---|---|---|---|---|
| series:KXECULPBTTS YES-price 30%-70% buy YES | 5 | +48.6 | [+47.1, +50.1] | None | None | — (0) | 0 | ·YY· |  |
| series:KXCANPLGAME YES-price 30%-70% buy NO | 6 | +45.7 | [+36.6, +54.7] | None | None | — (0) | 0 | ·YY· |  |
| series:KXLIGAMXBTTS YES-price 30%-70% buy YES | 5 | +38.6 | [+35.3, +41.9] | None | None | — (0) | 0 | ·YY· |  |
| series:KXMLSBTTS YES-price 30%-70% buy YES | 6 | +31.2 | [+28.8, +33.5] | None | None | -17.0 (6) | 0 | ·YY· |  |
| series:KXNHL2PSPREAD YES-price 10%-30% buy YES | 5 | +62.2 | [+22.8, +101.6] | None | 62.2 | +42.2 (5) | 0.0016 | ·YY· |  |
| series:KXLIGAMX1HTOTAL YES-price 70%-90% buy YES | 6 | +23.0 | [+21.9, +24.1] | None | None | — (0) | 0 | ·YY· |  |
| series:KXHNLGAME YES-price 70%-90% buy YES | 5 | +22.6 | [+18.7, +26.5] | None | None | — (0) | 0 | ·YY· |  |
| series:KXVENFUTVETOTAL YES-price 70%-90% buy YES | 5 | +20.7 | [+18.1, +23.3] | None | None | — (0) | 0 | ·YY· |  |
| family:KXVENFUTVE YES-price 70%-90% buy YES | 5 | +20.7 | [+18.1, +23.3] | None | None | — (0) | 0 | ·YY· |  |
| series:KXACBGAME YES-price 70%-90% buy YES | 6 | +22.2 | [+17.6, +26.7] | None | None | — (0) | 0 | ·YY· |  |
| family:KXACB YES-price 70%-90% buy YES | 6 | +22.2 | [+17.6, +26.7] | None | None | — (0) | 0 | ·YY· |  |
| series:KXUSL1H YES-price 30%-70% buy NO | 14 | +31.2 | [+16.7, +45.7] | None | 27.6 | — (0) | 1.7e-05 | ·YY· |  |
| series:KXLOLTOTALMAPS YES-price 10%-30% buy NO | 5 | +21.2 | [+16.1, +26.3] | None | None | — (0) | 0 | ·YY· |  |
| series:KXLIGAMXTOTAL YES-price 70%-90% buy YES | 6 | +17.3 | [+16.1, +18.6] | None | None | — (0) | 0 | ·YY· |  |
| series:KXNHLOT YES-price 10%-30% buy NO | 6 | +17.3 | [+16.0, +18.7] | None | 17.33 | — (0) | 0 | ·YY· |  |
| series:KXLIGAMX1HSCORE YES-price 10%-30% buy NO | 5 | +19.8 | [+15.9, +23.7] | None | None | — (0) | 0 | ·YY· |  |
| series:KXWTAMATCH YES-price 70%-90% buy YES | 11 | +18.3 | [+14.8, +21.7] | None | 16.86 | — (0) | 0 | ·YY· |  |
| series:KXUSLTOTAL YES-price 70%-90% buy YES | 7 | +16.1 | [+14.8, +17.5] | None | None | — (0) | 0 | ·YY· |  |
| series:KXDIESELW YES-price 10%-30% buy NO | 5 | +16.0 | [+14.7, +17.3] | None | None | — (0) | 0 | ·YY· |  |
| series:KXBIGGESTQUAKE YES-price 10%-30% buy NO | 6 | +18.4 | [+14.5, +22.3] | None | None | — (0) | 0 | ·YY· |  |
| family:KXURYPD YES-price 10%-30% buy NO | 5 | +17.3 | [+14.4, +20.1] | None | None | — (0) | 0 | ·YY· |  |
| series:KXWTAGTOTAL YES-price 70%-90% buy YES | 5 | +14.6 | [+12.8, +16.4] | None | None | — (0) | 0 | ·YY· |  |
| series:KXMLSFTTS YES-price 30%-70% buy YES | 7 | +29.3 | [+11.9, +46.6] | 29.33 | None | — (0) | 0.00074 | ·YY· |  |
| series:KXURYPDGAME YES-price 10%-30% buy NO | 5 | +15.3 | [+11.7, +18.9] | None | None | — (0) | 0 | ·YY· |  |
| series:KXNCAAFFIRSTTDTEAM YES-price 70%-90% buy YES | 17 | +16.4 | [+11.0, +21.8] | 13.91 | 21.0 | — (0) | 1.2e-09 | ·YY· |  |
