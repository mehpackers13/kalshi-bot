# Strategy Lab — 2026-11-08T16:02:34Z

4500 settled markets, 480 rules tested (group x price bucket x side, taker fees included).
**Rules passing the gate: 10** (>=30 events, >=+1c, CI above 0, positive in both halves).

| Rule | Events | Net c/contract | 95% range | Older half | Newer half | Pass |
|---|---|---|---|---|---|---|
| series:KXTSAD YES-price 30%-70% buy YES | 5 | +46.6 | [+35.2, +58.0] | None | None |  |
| series:KXHIGHDEN YES-price 70%-90% buy YES | 6 | +20.9 | [+18.1, +23.6] | None | None |  |
| series:KXHIGHTOKC YES-price 10%-30% buy NO | 6 | +20.4 | [+16.8, +24.1] | None | None |  |
| series:KXHIGHTLV YES-price 70%-90% buy YES | 5 | +20.5 | [+16.4, +24.5] | None | None |  |
| series:KXNATGASW YES-price 10%-30% buy NO | 5 | +20.6 | [+16.3, +24.9] | None | None |  |
| series:KXHIGHTLV YES-price 10%-30% buy NO | 8 | +19.4 | [+16.2, +22.6] | 19.45 | None |  |
| series:KXJ2LEAGUETOTAL YES-price 10%-30% buy NO | 8 | +19.1 | [+15.2, +23.1] | None | 19.15 |  |
| series:KXF1RACEPODIUM YES-price 70%-90% buy YES | 5 | +19.1 | [+14.8, +23.4] | None | None |  |
| series:KXLOLGAME YES-price 10%-30% buy NO | 9 | +17.6 | [+14.7, +20.6] | None | 18.17 |  |
| category:Crypto YES-price 70%-90% buy YES | 6 | +18.4 | [+14.5, +22.3] | 18.41 | None |  |
| series:KXHIGHTSFO YES-price 70%-90% buy YES | 5 | +19.2 | [+13.9, +24.5] | 19.17 | None |  |
| series:KXLOWTNOLA YES-price 10%-30% buy NO | 6 | +17.7 | [+13.4, +21.9] | 17.7 | None |  |
| series:KXHIGHTSEA YES-price 10%-30% buy NO | 10 | +16.9 | [+13.2, +20.7] | 16.19 | None |  |
| series:KXWTIW YES-price 10%-30% buy NO | 7 | +15.1 | [+13.1, +17.2] | 15.07 | None |  |
| series:KXHIGHTMIN YES-price 10%-30% buy NO | 9 | +16.0 | [+12.8, +19.2] | 14.98 | None |  |
| series:KXHIGHTSFO YES-price 10%-30% buy NO | 6 | +15.5 | [+12.7, +18.4] | 14.65 | None |  |
| series:KXNFLTD YES-price 10%-30% buy NO | 5 | +15.5 | [+12.4, +18.6] | None | 15.54 |  |
| series:KXCONMEBOLSUD1HBTTS YES-price 10%-30% buy NO | 8 | +14.2 | [+12.4, +16.1] | 14.24 | None |  |
| series:KXTXERCOTPEAKD YES-price 10%-30% buy NO | 6 | +15.7 | [+12.3, +19.1] | None | 15.73 |  |
| series:KXHIGHTEWR YES-price 10%-30% buy NO | 8 | +15.2 | [+12.2, +18.3] | 15.28 | None |  |
| series:KXUST2AD YES-price 10%-30% buy NO | 8 | +14.8 | [+12.2, +17.5] | None | None |  |
| series:KXTSAD YES-price 10%-30% buy NO | 6 | +16.0 | [+11.4, +20.6] | None | 16.02 |  |
| series:KXBRENTW YES-price 70%-90% buy YES | 5 | +16.5 | [+11.1, +21.8] | None | None |  |
| series:KXHIGHTDC YES-price 10%-30% buy NO | 6 | +17.4 | [+10.7, +24.1] | 15.93 | None |  |
| series:KXAAAGASDTX YES-price 10%-30% buy NO | 5 | +12.9 | [+10.5, +15.4] | None | 12.92 |  |
