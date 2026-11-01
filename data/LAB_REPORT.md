# Strategy Lab — 2026-11-01T15:54:19Z

3000 settled markets, 352 rules tested (group x price bucket x side, taker fees included).
**Rules passing the gate: 8** (>=30 events, >=+1c, CI above 0, positive in both halves).

| Rule | Events | Net c/contract | 95% range | Older half | Newer half | Pass |
|---|---|---|---|---|---|---|
| series:KXTSAD YES-price 30%-70% buy YES | 5 | +46.6 | [+35.2, +58.0] | None | 46.58 |  |
| series:KXHIGHTOKC YES-price 10%-30% buy NO | 6 | +20.4 | [+16.8, +24.1] | None | None |  |
| series:KXHIGHTLV YES-price 70%-90% buy YES | 5 | +20.5 | [+16.4, +24.5] | None | None |  |
| series:KXNATGASW YES-price 10%-30% buy NO | 5 | +20.6 | [+16.3, +24.9] | None | None |  |
| series:KXHIGHTLV YES-price 10%-30% buy NO | 8 | +19.4 | [+16.2, +22.6] | None | 19.2 |  |
| series:KXF1RACEPODIUM YES-price 70%-90% buy YES | 5 | +19.1 | [+14.8, +23.4] | None | None |  |
| series:KXLOLGAME YES-price 10%-30% buy NO | 9 | +17.6 | [+14.7, +20.6] | None | 18.17 |  |
| series:KXHIGHTSFO YES-price 70%-90% buy YES | 5 | +19.2 | [+13.9, +24.5] | None | None |  |
| series:KXLOWTNOLA YES-price 10%-30% buy NO | 6 | +17.7 | [+13.4, +21.9] | 17.0 | None |  |
| series:KXAAAGASDNE YES-price 10%-30% buy NO | 5 | +16.5 | [+12.8, +20.2] | None | 16.54 |  |
| series:KXHIGHTSFO YES-price 10%-30% buy NO | 6 | +15.5 | [+12.7, +18.4] | None | None |  |
| series:KXNFLTD YES-price 10%-30% buy NO | 5 | +15.5 | [+12.4, +18.6] | None | 15.54 |  |
| series:KXCONMEBOLSUD1HBTTS YES-price 10%-30% buy NO | 8 | +14.2 | [+12.4, +16.1] | 14.25 | None |  |
| series:KXHIGHTEWR YES-price 10%-30% buy NO | 8 | +15.2 | [+12.2, +18.3] | None | 15.99 |  |
| series:KXUST2AD YES-price 10%-30% buy NO | 8 | +14.8 | [+12.2, +17.5] | None | 13.95 |  |
| series:KXTSAD YES-price 10%-30% buy NO | 6 | +16.0 | [+11.4, +20.6] | None | 16.02 |  |
| series:KXHIGHTDC YES-price 10%-30% buy NO | 6 | +17.4 | [+10.7, +24.1] | None | None |  |
| category:Climate and Weather YES-price 10%-30% buy NO | 59 | +13.3 | [+8.9, +17.7] | 11.82 | 15.66 | YES |
| series:KXHNLGAME YES-price 10%-30% buy YES | 12 | +35.8 | [+8.7, +62.9] | 36.44 | None |  |
| category:Economics YES-price 10%-30% buy NO | 44 | +13.3 | [+8.4, +18.1] | 5.03 | 15.68 | YES |
| series:KXVENFUTVETOTAL YES-price 90%-100% buy YES | 8 | +8.1 | [+7.5, +8.7] | 7.8 | None |  |
| category:Climate and Weather YES-price 70%-90% buy YES | 47 | +11.8 | [+4.7, +18.9] | 7.63 | 19.08 | YES |
| category:Financials YES-price 10%-30% buy NO | 25 | +12.1 | [+4.3, +19.8] | 9.44 | 15.95 |  |
| series:KXLOWTDC YES-price 90%-100% buy YES | 8 | +4.7 | [+3.2, +6.2] | None | 3.63 |  |
| series:KXGOLDD YES-price 90%-100% buy YES | 5 | +3.2 | [+2.0, +4.3] | None | 3.17 |  |
