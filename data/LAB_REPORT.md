# Strategy Lab — 2026-11-11T16:46:06Z

4500 settled markets (4441 with executable candle quotes), 511 rules tested (group x YES-price bucket x side, taker fees included, entry = first traded hourly candle ask/bid).
**Rules passing both gates: 0** (executable rows only; >=30 events, >=+1c, CI above 0, positive in both halves, AND still positive after 1c extra adverse selection). Old VWAP method would have passed 10.
These are in-sample candidates for paper testing, not proven edges.

| Rule | Events | n_exec/n_approx | Net c | 95% range | Older | Newer | Net c -1c | Pass |
|---|---|---|---|---|---|---|---|---|
| series:KXBRENTW YES-price 10%-30% buy NO | 5 | 5/0 | +21.4 | [+17.6, +25.2] | None | None | +20.4 |  |
| series:KXLOLGAME YES-price 70%-90% buy YES | 9 | 9/0 | +16.9 | [+13.9, +19.9] | 16.0 | None | +15.9 |  |
| series:KXLOLGAME YES-price 10%-30% buy NO | 10 | 10/0 | +16.1 | [+13.2, +19.0] | 14.4 | 17.8 | +15.1 |  |
| series:KXNFLTD YES-price 10%-30% buy NO | 5 | 17/0 | +15.2 | [+12.7, +17.7] | None | 15.23 | +14.2 |  |
| series:KXBRENTW YES-price 70%-90% buy YES | 5 | 5/0 | +18.4 | [+12.2, +24.6] | None | None | +17.4 |  |
| series:KXCONMEBOLSUD1HBTTS YES-price 10%-30% buy NO | 8 | 8/0 | +12.4 | [+10.9, +13.8] | 12.38 | None | +11.4 |  |
| series:KXLOWTDEN YES-price 30%-70% buy YES | 9 | 10/0 | +39.4 | [+10.8, +68.0] | 44.3 | None | +38.4 |  |
| series:KXWTIW YES-price 10%-30% buy NO | 5 | 6/0 | +11.0 | [+9.7, +12.3] | None | None | +10.0 |  |
| series:KXVENFUTVETOTAL YES-price 90%-100% buy YES | 8 | 8/0 | +7.8 | [+7.1, +8.4] | 7.5 | None | +6.8 |  |
| series:KXFIBAGAME YES-price 0%-10% buy NO | 5 | 5/0 | +4.6 | [+2.8, +6.5] | 4.6 | None | +3.6 |  |
| series:KXFINYLSPREAD YES-price 0%-10% buy NO | 15 | 21/0 | +3.4 | [+2.2, +4.7] | 3.43 | None | +2.4 |  |
| series:KXTSAD YES-price 90%-100% buy YES | 5 | 5/0 | +4.2 | [+2.1, +6.3] | None | None | +3.2 |  |
| series:KXGOLDD YES-price 0%-10% buy NO | 6 | 9/0 | +3.4 | [+1.6, +5.2] | None | 3.39 | +2.4 |  |
| series:KXLALIGASPREAD YES-price 0%-10% buy NO | 15 | 16/1 | +2.9 | [+1.5, +4.3] | 3.61 | 1.83 | +1.9 |  |
| series:KXLOWTDC YES-price 0%-10% buy NO | 12 | 17/0 | +2.9 | [+1.3, +4.6] | 3.08 | None | +1.9 |  |
| series:KXHIGHTOKC YES-price 0%-10% buy NO | 19 | 24/0 | +2.5 | [+1.2, +3.7] | 2.42 | 2.58 | +1.5 |  |
| series:KXWTIW YES-price 0%-10% buy NO | 8 | 34/0 | +1.8 | [+1.2, +2.4] | 1.53 | None | +0.8 |  |
| series:KXEPL1HSCORE YES-price 0%-10% buy NO | 8 | 21/2 | +2.0 | [+0.7, +3.3] | None | 2.01 | +1.0 |  |
| series:KXHIGHTLV YES-price 0%-10% buy NO | 15 | 20/0 | +1.5 | [+0.7, +2.3] | 1.5 | None | +0.5 |  |
| series:KXK2LEAGUESPREAD YES-price 0%-10% buy NO | 14 | 17/1 | +2.1 | [+0.6, +3.7] | 2.38 | None | +1.1 |  |
| series:KXAAAGASWNJ YES-price 90%-100% buy YES | 7 | 15/0 | +1.6 | [+0.5, +2.7] | 1.85 | None | +0.6 |  |
| series:KXHIGHTSFO YES-price 0%-10% buy NO | 16 | 20/0 | +1.6 | [+0.5, +2.6] | 1.55 | 1.6 | +0.6 |  |
| series:KXDIESELD YES-price 0%-10% buy NO | 8 | 15/0 | +1.4 | [+0.5, +2.2] | None | 1.35 | +0.4 |  |
| series:KXBRENTW YES-price 0%-10% buy NO | 6 | 10/0 | +1.8 | [+0.4, +3.3] | None | None | +0.8 |  |
| series:KXLOWTNOLA YES-price 0%-10% buy NO | 11 | 14/0 | +1.8 | [+0.4, +3.1] | 0.79 | None | +0.8 |  |
