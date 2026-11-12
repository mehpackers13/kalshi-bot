# Maker Lab — 2026-11-12T00:40:05Z

Tests the one Kalshi strategy with peer-reviewed evidence behind it: Burgi, Deng & Whelan (UCD, Jan 2026) find makers average **-9.64%** vs takers **-31.46%** over 313,972 contracts, and that *"Makers who buy contracts costing 50c and over earn a 2.6% rate of return"*.

Our bot is a pure taker buying longshots — the -60% bucket — which is a coherent explanation for the audited -37.55u on its own.

13517 executable settled markets; discovery on 9461, 4056 held out. Maker fee charged at 0.0 everywhere (it is 0 on most series, so this is conservative). 1.0c of adverse selection charged to every maker entry. Quotes wider than 2c are rejected: assuming a fill at the touch in a wide market books the spread as edge and is not a real trade.

## Replication by entry cost

| Entry cost | Events | Taker net | Maker net |
|---|---|---|---|
| 0%-10% | 1141 | -0.55c | +1.93c |
| 10%-30% | 1468 | -1.61c | +1.28c |
| 30%-50% | 1640 | -1.88c | +1.11c |
| 50%-70% | 1640 | -3.23c | +0.05c |
| 70%-90% | 1477 | -3.46c | +0.02c |
| 90%-100% | 1312 | -2.79c | -0.46c |

## Rules passing every gate: 0

Gates: >=30 independent events; >=+1c with the 95% CI above 0; still >=+1c on held-out data; and Benjamini-Hochberg at q=0.10 across all 503 rules (cutoff p<=0.01851).

**The maker numbers are an upper bound, not a forecast.** A resting order only fills when someone takes it, and it fills precisely when the market is moving against you. Settled candles cannot measure fill probability, so this assumes every post fills at the touch. Real maker returns in the paper (-9.64%) are far worse than crossing the spread for free would imply. Any pass needs forward paper testing with real resting orders, where fills are observed rather than assumed.

| Rule | Events | Maker net | 95% range | Taker net | Holdout | p | Pass |
|---|---|---|---|---|---|---|---|
| series:KXNCAAF1H cost 50%-70% buy NO | 5 | +36.40 | [+32.2, +40.6] | 34.2 | — (0) | 0 |  |
| series:KXMLBF3 cost 30%-50% buy YES | 13 | +40.58 | [+19.9, +61.3] | 38.08 | — (0) | 8.9e-05 |  |
| series:KXMLBTEAMTOTAL cost 70%-90% buy YES | 12 | +17.54 | [+15.3, +19.8] | 15.96 | — (0) | 0 |  |
| series:KXFINYLSPREAD cost 70%-90% buy NO | 8 | +17.00 | [+14.6, +19.4] | 15.12 | — (0) | 0 |  |
| category:Commodities cost 70%-90% buy YES | 6 | +16.83 | [+11.3, +22.4] | 15.5 | +4.7 (8) | 1.3e-09 |  |
| series:KXARGPREMDIVSPREAD cost 70%-90% buy NO | 6 | +17.50 | [+10.7, +24.4] | 15.83 | — (0) | 3.2e-07 |  |
| series:KXMLBSB cost 90%-100% buy NO | 8 | +7.81 | [+7.3, +8.3] | 6.5 | — (0) | 0 |  |
| series:KXVENFUTVETOTAL cost 90%-100% buy YES | 9 | +7.78 | [+7.0, +8.5] | 6.78 | — (0) | 0 |  |
| series:KXHNLGAME cost 10%-30% buy YES | 7 | +40.93 | [+5.0, +76.8] | 38.57 | — (0) | 0.023 |  |
| series:KXATPCHALLENGERMATCH cost 90%-100% buy NO | 6 | +6.17 | [+4.9, +7.5] | 5.17 | — (0) | 0 |  |
| series:KXLIGAMXTOTAL cost 90%-100% buy YES | 7 | +5.57 | [+4.8, +6.3] | 4.29 | — (0) | 0 |  |
| series:KXVENFUTVETOTAL cost 90%-100% buy NO | 5 | +5.60 | [+4.4, +6.8] | 3.6 | — (0) | 0 |  |
| series:KXWTASETWINNER cost 50%-70% buy YES | 5 | +28.70 | [+4.3, +53.1] | 26.4 | — (0) | 0.019 |  |
| series:KXFINYLSPREAD cost 90%-100% buy NO | 9 | +5.67 | [+4.3, +7.0] | 4.5 | — (0) | 2.2e-16 |  |
| series:KXMLBTOTAL cost 90%-100% buy YES | 12 | +4.67 | [+3.7, +5.7] | 3.54 | — (0) | 0 |  |
| series:KXUSLTOTAL cost 90%-100% buy YES | 7 | +4.71 | [+3.7, +5.8] | 3.57 | — (0) | 0 |  |
| series:KXMLBHIT cost 90%-100% buy NO | 11 | +5.09 | [+3.5, +6.6] | 4.45 | — (0) | 4.1e-11 |  |
| series:KXHIGHCHI cost 30%-50% buy YES | 5 | +19.50 | [+3.5, +35.5] | 17.4 | — (0) | 0.015 |  |
| series:KXBRASILEIROSPREAD cost 90%-100% buy NO | 6 | +5.25 | [+3.5, +7.0] | 3.92 | — (0) | 4e-09 |  |
| series:KXHIGHCHI cost 90%-100% buy NO | 5 | +3.07 | [+2.5, +3.6] | 2.07 | — (0) | 0 |  |
| series:KXHIGHTSFO cost 90%-100% buy NO | 14 | +2.65 | [+1.8, +3.5] | 1.83 | -2.9 (6) | 2e-09 |  |
| series:KXHIGHTBOS cost 90%-100% buy NO | 5 | +2.10 | [+1.5, +2.7] | 1.3 | — (0) | 2.4e-13 |  |
| category:Economics cost 90%-100% buy YES | 29 | +2.34 | [+1.5, +3.2] | 1.98 | -1.6 (22) | 2.1e-08 |  |
| series:KXMLSFTTS cost 90%-100% buy NO | 5 | +2.80 | [+1.5, +4.1] | — | — (0) | 2.4e-05 |  |
| series:KXHIGHPHIL cost 90%-100% buy NO | 5 | +2.03 | [+1.4, +2.6] | — | — (0) | 2.6e-12 |  |
