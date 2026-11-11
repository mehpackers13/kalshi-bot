# Maker Lab — 2026-11-11T20:30:28Z

Tests the one Kalshi strategy with peer-reviewed evidence behind it: Burgi, Deng & Whelan (UCD, Jan 2026) find makers average **-9.64%** vs takers **-31.46%** over 313,972 contracts, and that *"Makers who buy contracts costing 50c and over earn a 2.6% rate of return"*.

Our bot is a pure taker buying longshots — the -60% bucket — which is a coherent explanation for the audited -37.55u on its own.

5736 executable settled markets; discovery on 4015, 1721 held out. Maker fee charged at 0.0 everywhere (it is 0 on most series, so this is conservative). 1.0c of adverse selection charged to every maker entry. Quotes wider than 2c are rejected: assuming a fill at the touch in a wide market books the spread as edge and is not a real trade.

## Replication by entry cost

| Entry cost | Events | Taker net | Maker net |
|---|---|---|---|
| 0%-10% | 616 | -2.42c | -0.38c |
| 10%-30% | 640 | -1.81c | +1.52c |
| 30%-50% | 620 | -2.27c | +0.59c |
| 50%-70% | 620 | -2.41c | +0.59c |
| 70%-90% | 645 | -3.13c | -0.19c |
| 90%-100% | 747 | -1.06c | +1.29c |

## Rules passing every gate: 0

Gates: >=30 independent events; >=+1c with the 95% CI above 0; still >=+1c on held-out data; and Benjamini-Hochberg at q=0.10 across all 264 rules (cutoff p<=0.01978).

**The maker numbers are an upper bound, not a forecast.** A resting order only fills when someone takes it, and it fills precisely when the market is moving against you. Settled candles cannot measure fill probability, so this assumes every post fills at the touch. Real maker returns in the paper (-9.64%) are far worse than crossing the spread for free would imply. Any pass needs forward paper testing with real resting orders, where fills are observed rather than assumed.

| Rule | Events | Maker net | 95% range | Taker net | Holdout | p | Pass |
|---|---|---|---|---|---|---|---|
| series:KXNCAAF1HSPREAD cost 30%-50% buy NO | 5 | +57.10 | [+52.9, +61.3] | 55.0 | +31.1 (8) | 0 |  |
| series:KXATPCHALLENGERMATCH cost 50%-70% buy YES | 6 | +43.00 | [+38.9, +47.1] | 40.83 | — (0) | 0 |  |
| series:KXNCAAF1QSPREAD cost 70%-90% buy NO | 6 | +24.08 | [+21.9, +26.3] | 21.58 | — (0) | 0 |  |
| series:KXLOLGAME cost 70%-90% buy NO | 7 | +20.43 | [+16.1, +24.8] | 18.43 | — (0) | 0 |  |
| series:KXNCAAF1Q cost 70%-90% buy NO | 11 | +18.00 | [+15.5, +20.5] | 16.27 | — (0) | 0 |  |
| series:KXFINYLSPREAD cost 70%-90% buy NO | 8 | +17.00 | [+14.6, +19.4] | 15.12 | — (0) | 0 |  |
| series:KXNFLTD cost 70%-90% buy NO | 5 | +17.03 | [+14.5, +19.6] | 15.63 | — (0) | 0 |  |
| series:KXVENFUTVETOTAL cost 70%-90% buy YES | 5 | +14.00 | [+9.5, +18.5] | 12.5 | — (0) | 5.7e-10 |  |
| series:KXVENFUTVETOTAL cost 90%-100% buy YES | 6 | +8.33 | [+7.9, +8.8] | 7.33 | — (0) | 0 |  |
| series:KXHNLGAME cost 10%-30% buy YES | 9 | +39.17 | [+6.5, +71.9] | 37.0 | — (0) | 0.017 |  |
| series:KXNCAAFGAME cost 90%-100% buy NO | 10 | +6.30 | [+4.8, +7.8] | 5.3 | +4.0 (5) | 0 |  |
| series:KXNCAAFGAME cost 90%-100% buy YES | 10 | +6.20 | [+4.7, +7.7] | 5.2 | +3.8 (5) | 2.2e-16 |  |
| series:KXNCAAF2H cost 90%-100% buy NO | 8 | +5.63 | [+4.5, +6.8] | 4.25 | — (0) | 0 |  |
| series:KXFINYLSPREAD cost 90%-100% buy NO | 9 | +5.67 | [+4.3, +7.0] | 4.5 | — (0) | 2.2e-16 |  |
| series:KXNCAAFTEAMTOTAL cost 90%-100% buy YES | 8 | +5.75 | [+4.2, +7.2] | 4.63 | — (0) | 1.8e-14 |  |
| series:KXNCAAFSPREAD cost 90%-100% buy YES | 5 | +6.20 | [+3.0, +9.4] | — | — (0) | 0.0001 |  |
| series:KXUFCMOV cost 90%-100% buy NO | 7 | +3.52 | [+2.1, +4.9] | 2.48 | -0.7 (5) | 4.3e-07 |  |
| series:KXLOWTDEN cost 90%-100% buy NO | 8 | +2.00 | [+1.6, +2.4] | 1.0 | — (0) | 0 |  |
| series:KXLALIGASPREAD cost 90%-100% buy NO | 11 | +2.91 | [+1.6, +4.2] | 2.15 | — (0) | 8.4e-06 |  |
| series:KXHIGHTOKC cost 90%-100% buy NO | 18 | +2.56 | [+1.6, +3.5] | 2.0 | — (0) | 1.7e-07 |  |
| category:Sports cost 90%-100% buy YES | 73 | +4.16 | [+1.4, +7.0] | 3.44 | -4.3 (39) | 0.003 |  |
| category:Commodities cost 90%-100% buy YES | 28 | +2.37 | [+1.3, +3.4] | 2.44 | — (0) | 1e-05 |  |
| series:KXHIGHDEN cost 90%-100% buy NO | 13 | +1.75 | [+1.2, +2.3] | 0.73 | +3.0 (7) | 1.8e-10 |  |
| series:KXHIGHTLV cost 90%-100% buy NO | 15 | +1.67 | [+1.2, +2.2] | 1.07 | — (0) | 3.7e-11 |  |
| series:KXLOWTNOLA cost 90%-100% buy NO | 5 | +2.00 | [+1.1, +2.9] | 0.4 | — (0) | 7.7e-06 |  |
