# Strategy Lab: how it works and how far to trust it

The lab asks one question every week: across every Kalshi category, did buying at a certain price
level make money after fees, on markets that have already settled?

## What it does
1. Collects settled, liquid markets (volume 200 or more) from the last 90 days, across categories.
2. For each one it records the price a real buyer could have paid about 3 to 36 hours before close:
   the first hourly candlestick in that window with trading volume. Buying YES costs that candle's
   ask. Buying NO costs 1 minus that candle's bid. Kalshi's taker fee is added on top.
3. Groups markets by category or series, by price bucket and by side, and measures profit per
   contract. Ladders of strikes on the same event count as one outcome (clustered by event), and
   the 95% range is the mean plus or minus two standard errors across events.

## Why the old numbers were too good
The first version used the volume-weighted average trade price (VWAP). That is a price somebody
traded at, not a price you can get. A taker crosses the spread: pays the ask to buy YES, or
sells into the bid. On thin markets that gap is several cents, which is bigger than the edges
the lab was finding. Result: price-bucket rules that "passed" in-sample lost money in forward
paper testing (longshot rule: about -3.9c per contract over 429 events).

## The two gates
A rule PASSES only if it clears both, using executable-price rows only:
1. Base gate: at least 30 independent events, mean net at least +1c per contract, 95% range above
   zero, and positive in both the older half and the newer half of the data.
2. Adverse-selection gate: still positive after taking another 1c off (net minus 1c is at least
   zero and the lower bound minus 1c is above zero). This covers prices moving against us between
   signal and fill.

Rows that have no candle quote yet use VWAP plus a 2c spread penalty ("vwap+2c"). They are shown in
the report (n_exec vs n_approx) but cannot make a rule pass. Backfill them with `--requote N`.

## What a pass means
Nothing more than "worth paper testing". Every passed rule is an in-sample candidate: we picked it
because it looked good on past data, and with hundreds of rules tested some will look good by luck.
Passed rules are written to `data/lab_results.json` with a `paper_rule` key. `rules/lab_rules.py`
paper-trades them (pretend bets, 10 per rule at most). The paper engine's kill switch retires a rule
that fails forward. Only a rule that survives forward paper testing is even a candidate for real money,
and that decision is made by a human.

## Running it
    python strategy_lab.py --new 1200 --requote 1500   # weekly workflow
    python strategy_lab.py --analyse-only              # re-score the cache
