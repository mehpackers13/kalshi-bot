# Maker Lab — 2026-11-11T20:02:42Z

Tests the one Kalshi strategy with peer-reviewed evidence behind it: Burgi, Deng & Whelan (UCD, Jan 2026) find makers average **-9.64%** vs takers **-31.46%** over 313,972 contracts, and that *"Makers who buy contracts costing 50c and over earn a 2.6% rate of return"*.

Our bot is a pure taker buying longshots — the -60% bucket — which is a coherent explanation for the audited -37.55u on its own.

4447 executable settled markets; discovery on 3112, 1335 held out. Maker fee charged at 0.0175 everywhere (it is 0 on most series, so this is conservative). 1.0c of adverse selection charged to every maker entry. Quotes wider than 2c are rejected: assuming a fill at the touch in a wide market books the spread as edge and is not a real trade.

## Replication by entry cost

| Entry cost | Events | Taker net | Maker net |
|---|---|---|---|
| 0%-10% | 569 | -2.34c | -1.39c |
| 10%-30% | 520 | -2.35c | +0.21c |
| 30%-50% | 477 | -0.89c | +1.09c |
| 50%-70% | 477 | -3.08c | -1.91c |
| 70%-90% | 525 | -3.16c | -0.86c |
| 90%-100% | 698 | -0.91c | +0.25c |

## Rules passing every gate: 0

Gates: >=30 independent events; >=+1c with the 95% CI above 0; still >=+1c on held-out data; and Benjamini-Hochberg at q=0.10 across all 258 rules (cutoff p<=0.02552).

**The maker numbers are an upper bound, not a forecast.** A resting order only fills when someone takes it, and it fills precisely when the market is moving against you. Settled candles cannot measure fill probability, so this assumes every post fills at the touch. Real maker returns in the paper (-9.64%) are far worse than crossing the spread for free would imply. Any pass needs forward paper testing with real resting orders, where fills are observed rather than assumed.

| Rule | Events | Maker net | 95% range | Taker net | Holdout | p | Pass |
|---|---|---|---|---|---|---|---|
| series:KXATPCHALLENGERMATCH cost 50%-70% buy YES | 5 | +44.40 | [+41.1, +47.7] | 43.2 | — (0) | 0 |  |
| series:KXLOLGAME cost 70%-90% buy NO | 6 | +18.00 | [+14.2, +21.8] | 17.17 | — (0) | 0 |  |
| series:KXFINYLSPREAD cost 70%-90% buy NO | 8 | +16.00 | [+13.6, +18.4] | 15.12 | — (0) | 0 |  |
| series:KXNFLTD cost 70%-90% buy NO | 5 | +16.03 | [+13.5, +18.6] | 15.63 | — (0) | 0 |  |
| series:KXNCAAF1Q cost 70%-90% buy NO | 6 | +17.67 | [+13.4, +21.9] | 17.17 | — (0) | 2.2e-16 |  |
| series:KXNCAAFGAME cost 70%-90% buy YES | 9 | +16.22 | [+12.6, +19.9] | 15.78 | -2.3 (13) | 0 |  |
| series:KXVENFUTVETOTAL cost 70%-90% buy YES | 5 | +13.00 | [+8.5, +17.5] | 12.5 | — (0) | 8.6e-09 |  |
| series:KXVENFUTVETOTAL cost 90%-100% buy YES | 6 | +7.33 | [+6.9, +7.8] | 7.33 | — (0) | 0 |  |
| series:KXHNLGAME cost 10%-30% buy YES | 9 | +38.17 | [+5.5, +70.9] | 37.0 | — (0) | 0.02 |  |
| series:KXNCAAFTOTAL cost 90%-100% buy NO | 5 | +5.00 | [+4.4, +5.6] | 5.0 | -33.4 (5) | 0 |  |
| series:KXNCAAFSPREAD cost 90%-100% buy NO | 13 | +4.93 | [+4.0, +5.8] | 4.91 | -12.2 (14) | 0 |  |
| series:KXNCAAFGAME cost 90%-100% buy NO | 6 | +4.67 | [+4.0, +5.3] | 4.67 | — (0) | 0 |  |
| series:KXNCAAFGAME cost 90%-100% buy YES | 6 | +4.50 | [+3.6, +5.4] | 4.5 | — (0) | 0 |  |
| series:KXFINYLSPREAD cost 90%-100% buy NO | 9 | +4.67 | [+3.3, +6.0] | 4.5 | — (0) | 1.1e-11 |  |
| series:KXNCAAFSPREAD cost 30%-50% buy YES | 24 | +18.88 | [+1.5, +36.3] | 17.77 | -13.0 (25) | 0.03 |  |
| series:KXUFCMOV cost 90%-100% buy NO | 8 | +2.33 | [+1.1, +3.6] | 2.29 | — (0) | 0.00023 |  |
| series:KXGOLDW cost 90%-100% buy NO | 5 | +1.19 | [+0.7, +1.7] | 1.27 | — (0) | 6.3e-07 |  |
| series:KXLALIGASPREAD cost 90%-100% buy NO | 11 | +1.91 | [+0.6, +3.2] | 2.15 | — (0) | 0.0035 |  |
| series:KXHIGHTOKC cost 90%-100% buy NO | 19 | +1.51 | [+0.6, +2.5] | 1.94 | — (0) | 0.0014 |  |
| series:KXDIESELD cost 90%-100% buy NO | 7 | +1.64 | [+0.6, +2.7] | 2.5 | — (0) | 0.0025 |  |
| category:Commodities cost 90%-100% buy YES | 32 | +1.51 | [+0.5, +2.5] | 2.56 | — (0) | 0.0031 |  |
| series:KXLOWTDEN cost 90%-100% buy NO | 9 | +0.89 | [+0.5, +1.3] | 0.89 | — (0) | 9.1e-06 |  |
| series:KXAAAGASDNE cost 90%-100% buy NO | 7 | +1.44 | [+0.3, +2.5] | 1.95 | — (0) | 0.009 |  |
| series:KXHIGHDEN cost 90%-100% buy NO | 18 | +1.31 | [+0.2, +2.4] | 1.44 | — (0) | 0.016 |  |
| series:KXHIGHTLV cost 90%-100% buy NO | 14 | +0.71 | [+0.2, +1.2] | 1.08 | — (0) | 0.0072 |  |
