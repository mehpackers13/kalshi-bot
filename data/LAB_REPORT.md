# Strategy Lab — 2026-11-18T01:49:26Z

121637 settled markets (121554 with executable candle quotes), 4850 rules tested (group x YES-price bucket x side, taker fees included, entry = first traded hourly candle ask/bid).
Discovery used the oldest 85145 markets; the newest 36492 were held out and never used to pick a rule.

**Rules passing all four gates: 2.** A rule must clear:

1. **economic** — >=30 events, >=+1c/contract, 95% CI above 0, positive in both halves;
2. **adverse selection** — still positive after 1c extra slippage;
3. **multiple comparisons** — Benjamini-Hochberg at q=0.10 over all 4850 rules tested together (cutoff p<=0.02327). Without this, ~1 rule in 20 clears a 95% CI by pure chance, so a larger history yields MORE fake edges, not fewer;
4. **out of sample** — >=10 events in the held-out newest slice and >=+1c there too.

2 rules cleared gates 1, 2 and 4; 2 of those survived the FDR correction. The old VWAP method, with no fees, spread, FDR or holdout, would have passed 29.
A pass is a candidate for forward paper testing, not a proven edge, and never a live bet.

| Rule | Events | Net c | 95% range | Older | Newer | Holdout (n) | p | Gates 1/2/3/4 | Pass |
|---|---|---|---|---|---|---|---|---|---|
| series:KXEREDIVISIE1HTOTAL YES-price 30%-70% buy YES | 5 | +52.2 | [+49.9, +54.5] | None | None | — (0) | 0 | ·YY· |  |
| series:KXTFF1LIGBTTS YES-price 30%-70% buy YES | 6 | +41.0 | [+38.4, +43.6] | None | None | — (0) | 0 | ·YY· |  |
| series:KXTACAPORTSPREAD YES-price 30%-70% buy NO | 7 | +41.9 | [+37.4, +46.4] | 41.93 | None | — (0) | 0 | ·YY· |  |
| series:KXBUNDESLIGABTTS YES-price 30%-70% buy YES | 6 | +32.7 | [+31.0, +34.4] | None | None | — (0) | 0 | ·YY· |  |
| series:KXNBAPTSLEADER YES-price 10%-30% buy YES | 21 | +46.8 | [+27.4, +66.2] | None | 44.78 | -17.3 (6) | 1.4e-06 | ·YY· |  |
| series:KXALEAGUE1HTOTAL YES-price 70%-90% buy YES | 5 | +24.8 | [+22.4, +27.2] | None | 24.8 | — (0) | 0 | ·YY· |  |
| series:KXWNBATOTAL YES-price 10%-30% buy NO | 5 | +23.0 | [+21.9, +24.1] | None | None | — (0) | 0 | ·YY· |  |
| series:KXLIGAMX1HTOTAL YES-price 70%-90% buy YES | 9 | +23.1 | [+21.8, +24.4] | None | 22.67 | — (0) | 0 | ·YY· |  |
| series:KXNFL4QTOTAL YES-price 70%-90% buy YES | 7 | +23.7 | [+20.6, +26.9] | 25.0 | None | — (0) | 0 | ·YY· |  |
| family:KXSERIEB YES-price 70%-90% buy YES | 6 | +20.7 | [+19.0, +22.4] | None | None | — (0) | 0 | ·YY· |  |
| series:KXSERIEBTOTAL YES-price 70%-90% buy YES | 6 | +20.7 | [+19.0, +22.4] | None | None | — (0) | 0 | ·YY· |  |
| series:KXEFLCUP1HTOTAL YES-price 70%-90% buy YES | 7 | +21.1 | [+18.9, +23.4] | None | 21.14 | — (0) | 0 | ·YY· |  |
| series:KXAUTBUNDESTOTAL YES-price 70%-90% buy YES | 6 | +20.8 | [+18.8, +22.9] | None | None | — (0) | 0 | ·YY· |  |
| series:KXLIGUE11H YES-price 10%-30% buy NO | 6 | +22.1 | [+18.2, +25.9] | None | None | — (0) | 0 | ·YY· |  |
| series:KXLIGUE11HBTTS YES-price 10%-30% buy NO | 6 | +19.0 | [+18.1, +19.9] | None | 19.0 | — (0) | 0 | ·YY· |  |
| family:KXROML1 YES-price 70%-90% buy YES | 6 | +20.2 | [+18.0, +22.5] | None | None | — (0) | 0 | ·YY· |  |
| series:KXATPGSPREAD YES-price 70%-90% buy YES | 6 | +20.3 | [+18.0, +22.7] | None | None | — (0) | 0 | ·YY· |  |
| series:KXMLSTEAMTOTAL YES-price 70%-90% buy YES | 5 | +22.2 | [+17.9, +26.5] | None | None | — (0) | 0 | ·YY· |  |
| series:KXBSLGAME YES-price 70%-90% buy YES | 5 | +20.2 | [+17.1, +23.3] | None | None | — (0) | 0 | ·YY· |  |
| series:KXALLSVENSKANTOTAL YES-price 10%-30% buy NO | 8 | +18.4 | [+17.1, +19.6] | None | None | — (0) | 0 | ·YY· |  |
| series:KXMLSTEAMTOTAL YES-price 10%-30% buy NO | 5 | +21.4 | [+17.1, +25.7] | None | None | — (0) | 0 | ·YY· |  |
| series:KXETTANSPREAD YES-price 10%-30% buy NO | 5 | +19.8 | [+17.0, +22.6] | None | None | — (0) | 0 | ·YY· |  |
| family:KXBSL YES-price 70%-90% buy YES | 6 | +19.7 | [+16.9, +22.4] | 18.6 | None | — (0) | 0 | ·YY· |  |
| series:KXROML1TOTAL YES-price 70%-90% buy YES | 6 | +19.5 | [+16.6, +22.4] | None | None | — (0) | 0 | ·YY· |  |
| series:KXEPLTOTAL YES-price 70%-90% buy YES | 11 | +18.2 | [+16.2, +20.2] | 20.2 | 16.5 | — (0) | 0 | ·YY· |  |
