# Fill Lab — 2026-11-12T04:37:55Z

Measures the one number maker_lab.py assumes: whether a resting order fills, and whether filling means you were wrong.

3000 harvested markets, buying YES as a maker, spread <= 2c, entry window 36h-3h before close. A fill is counted only when a trade printed strictly THROUGH our resting price with the taker on the opposite side, since at our own price we cannot know our queue position.

- **Fill rate: 45.8%**

- all markets (maker_lab's assumption): **+1.09c** [-0.45, +2.63] on n=2762
- would have filled: **-1.72c** [-4.08, +0.63] on n=1264
- would NOT have filled: **+3.41c** [+1.38, +5.44] on n=1496

**Adverse selection: +2.81c/contract.** This is the amount maker_lab overstates the maker case by, because it scores every market rather than only the ones a resting order would actually have caught.

No trade data for 2 markets; 0 API errors.

Research only. Nothing here places an order.
