# Strategy Lab — 2026-11-12T12:12:16Z

16817 settled markets (16758 with executable candle quotes), 1086 rules tested (group x YES-price bucket x side, taker fees included, entry = first traded hourly candle ask/bid).
Discovery used the oldest 11771 markets; the newest 5046 were held out and never used to pick a rule.

**Rules passing all four gates: 0.** A rule must clear:

1. **economic** — >=30 events, >=+1c/contract, 95% CI above 0, positive in both halves;
2. **adverse selection** — still positive after 1c extra slippage;
3. **multiple comparisons** — Benjamini-Hochberg at q=0.10 over all 1086 rules tested together (cutoff p<=0.02571). Without this, ~1 rule in 20 clears a 95% CI by pure chance, so a larger history yields MORE fake edges, not fewer;
4. **out of sample** — >=10 events in the held-out newest slice and >=+1c there too.

0 rules cleared gates 1, 2 and 4; 0 of those survived the FDR correction. The old VWAP method, with no fees, spread, FDR or holdout, would have passed 6.
A pass is a candidate for forward paper testing, not a proven edge, and never a live bet.

| Rule | Events | Net c | 95% range | Older | Newer | Holdout (n) | p | Gates 1/2/3/4 | Pass |
|---|---|---|---|---|---|---|---|---|---|
| series:KXKLEAGUEBTTS YES-price 30%-70% buy YES | 5 | +42.4 | [+39.8, +45.0] | None | None | — (0) | 0 | ·YY· |  |
| series:KXNBLSPREAD YES-price 30%-70% buy NO | 5 | +40.7 | [+34.6, +46.8] | None | None | — (0) | 0 | ·YY· |  |
| series:KXJLEAGUE1HTOTAL YES-price 30%-70% buy NO | 5 | +31.4 | [+29.8, +33.0] | None | None | — (0) | 0 | ·YY· |  |
| family:KXLALIGA2 YES-price 70%-90% buy YES | 6 | +22.2 | [+21.0, +23.4] | None | None | — (0) | 0 | ·YY· |  |
| series:KXLALIGA2TOTAL YES-price 70%-90% buy YES | 6 | +22.2 | [+21.0, +23.4] | None | None | — (0) | 0 | ·YY· |  |
| series:KXLALIGA2GAME YES-price 10%-30% buy NO | 5 | +23.2 | [+20.1, +26.3] | None | None | — (0) | 0 | ·YY· |  |
| family:KXKLEAGUE YES-price 70%-90% buy YES | 5 | +21.6 | [+18.1, +25.1] | None | None | — (0) | 0 | ·YY· |  |
| family:KXEPL YES-price 30%-70% buy NO | 8 | +28.6 | [+16.4, +40.8] | None | 28.46 | -0.3 (6) | 2.6e-06 | ·YY· |  |
| series:KXKLEAGUETOTAL YES-price 70%-90% buy YES | 5 | +20.4 | [+16.3, +24.5] | None | None | — (0) | 0 | ·YY· |  |
| family:KXEREDIVISIE YES-price 10%-30% buy YES | 7 | +35.8 | [+14.1, +57.5] | None | 37.17 | — (0) | 0.00096 | ·YY· |  |
| series:KXJ2LEAGUETOTAL YES-price 10%-30% buy NO | 7 | +18.1 | [+14.1, +22.1] | None | None | +13.7 (8) | 0 | ·YY· |  |
| series:KXELITESERIENGAME YES-price 10%-30% buy NO | 5 | +18.3 | [+14.0, +22.6] | None | None | — (0) | 0 | ·YY· |  |
| series:KXLOLGAME YES-price 70%-90% buy YES | 9 | +16.9 | [+13.9, +19.9] | 16.0 | None | — (0) | 0 | ·YY· |  |
| series:KXLOLGAME YES-price 10%-30% buy NO | 10 | +16.1 | [+13.2, +19.0] | 14.4 | 17.8 | — (0) | 0 | ·YY· |  |
| family:KXELITESERIEN YES-price 10%-30% buy NO | 5 | +16.9 | [+12.8, +21.0] | None | None | — (0) | 2.2e-16 | ·YY· |  |
| series:KXCONMEBOLSUD1HBTTS YES-price 10%-30% buy NO | 8 | +12.4 | [+10.9, +13.8] | 12.14 | None | — (0) | 0 | ·YY· |  |
| series:KXWTIW YES-price 10%-30% buy NO | 5 | +11.0 | [+9.7, +12.3] | None | None | — (0) | 0 | ·YY· |  |
| series:KXJLEAGUE1HTOTAL YES-price 10%-30% buy NO | 6 | +16.0 | [+9.3, +22.7] | None | None | — (0) | 1.7e-06 | ·YY· |  |
| series:KXLALIGA2GAME YES-price 30%-70% buy YES | 5 | +25.2 | [+7.8, +42.6] | None | None | — (0) | 0.0038 | ·YY· |  |
| series:KXVENFUTVETOTAL YES-price 90%-100% buy YES | 8 | +7.8 | [+7.1, +8.4] | 7.6 | None | — (0) | 0 | ·YY· |  |
| family:KXELITESERIEN YES-price 30%-70% buy YES | 6 | +25.8 | [+5.9, +45.7] | None | None | — (0) | 0.0095 | ·YY· |  |
| series:KXNCAAFTEAMTOTAL YES-price 30%-70% buy NO | 18 | +20.5 | [+4.4, +36.6] | 23.45 | 12.98 | -0.5 (5) | 0.011 | ·YY· |  |
| family:KXLALIGA2 YES-price 10%-30% buy NO | 5 | +14.9 | [+4.4, +25.4] | None | None | — (0) | 0.0045 | ·YY· |  |
| family:KXJLEAGUE YES-price 90%-100% buy YES | 5 | +5.8 | [+4.3, +7.3] | None | None | — (0) | 3.1e-15 | ·YY· |  |
| series:KXJLEAGUETOTAL YES-price 90%-100% buy YES | 5 | +5.8 | [+4.3, +7.3] | None | None | — (0) | 3.1e-15 | ·YY· |  |
