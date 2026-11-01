# Strategy Lab — 2026-11-01T03:17:44Z

1500 settled markets, 194 rules tested (group x price bucket x side, taker fees included).
**Rules passing the gate: 3** (>=30 events, >=+1c, CI above 0, positive in both halves).

| Rule | Events | Net c/contract | 95% range | Older half | Newer half | Pass |
|---|---|---|---|---|---|---|
| series:KXHIGHTOKC YES-price 10%-30% buy NO | 6 | +20.4 | [+16.8, +24.1] | None | None |  |
| series:KXHIGHTLV YES-price 70%-90% buy YES | 5 | +20.5 | [+16.4, +24.5] | None | None |  |
| series:KXHIGHTLV YES-price 10%-30% buy NO | 8 | +19.4 | [+16.2, +22.6] | None | 18.97 |  |
| series:KXF1RACEPODIUM YES-price 70%-90% buy YES | 5 | +19.1 | [+14.8, +23.4] | None | None |  |
| series:KXLOLGAME YES-price 10%-30% buy NO | 9 | +17.6 | [+14.7, +20.6] | None | 18.17 |  |
| series:KXLOWTNOLA YES-price 10%-30% buy NO | 6 | +17.7 | [+13.4, +21.9] | 17.0 | None |  |
| series:KXNFLTD YES-price 10%-30% buy NO | 5 | +15.5 | [+12.4, +18.6] | None | 15.54 |  |
| series:KXCONMEBOLSUD1HBTTS YES-price 10%-30% buy NO | 8 | +14.2 | [+12.4, +16.1] | 14.25 | None |  |
| series:KXUST2AD YES-price 10%-30% buy NO | 8 | +14.8 | [+12.2, +17.5] | None | 13.95 |  |
| category:Economics YES-price 10%-30% buy NO | 15 | +13.5 | [+11.7, +15.4] | None | 12.58 |  |
| category:Climate and Weather YES-price 10%-30% buy NO | 34 | +14.7 | [+10.2, +19.1] | 17.33 | 11.25 | YES |
| series:KXVENFUTVETOTAL YES-price 90%-100% buy YES | 8 | +8.1 | [+7.5, +8.7] | None | 8.35 |  |
| series:KXLOWTDC YES-price 90%-100% buy YES | 8 | +4.7 | [+3.2, +6.2] | None | 3.63 |  |
| category:ALL YES-price 10%-30% buy NO | 205 | +6.9 | [+3.0, +10.9] | 5.4 | 9.2 | YES |
| series:KXLOWTTTN YES-price 90%-100% buy YES | 6 | +4.2 | [+1.9, +6.6] | None | None |  |
| series:KXLALIGASPREAD YES-price 0%-10% buy NO | 15 | +3.1 | [+1.8, +4.5] | 3.54 | 2.56 |  |
| series:KXLOWTSAN YES-price 0%-10% buy NO | 17 | +2.3 | [+1.7, +2.9] | 2.72 | 1.85 |  |
| category:Financials YES-price 10%-30% buy NO | 21 | +10.7 | [+1.6, +19.8] | 8.19 | 14.78 |  |
| category:Financials YES-price 0%-10% buy NO | 25 | +2.1 | [+1.3, +3.0] | 1.84 | 2.62 |  |
| series:KXLOWTNOLA YES-price 0%-10% buy NO | 15 | +2.2 | [+1.3, +3.1] | 1.7 | 3.13 |  |
| series:KXNFLTD YES-price 0%-10% buy NO | 5 | +2.6 | [+1.2, +3.9] | None | 2.59 |  |
| category:Economics YES-price 90%-100% buy YES | 30 | +1.9 | [+0.9, +2.8] | 4.62 | 0.85 | YES |
| series:KXLOWTDC YES-price 0%-10% buy NO | 15 | +1.9 | [+0.8, +2.9] | 1.46 | 2.47 |  |
| series:KXK2LEAGUESPREAD YES-price 0%-10% buy NO | 13 | +2.1 | [+0.7, +3.5] | 2.4 | None |  |
| series:KXUST5AD YES-price 0%-10% buy NO | 5 | +1.9 | [+0.7, +3.0] | None | None |  |
