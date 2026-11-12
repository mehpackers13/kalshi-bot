# Fill Lab — 2026-11-12T04:53:25Z

Measures the one number maker_lab.py assumes: whether a resting order fills, and whether filling means you were wrong.

3000 harvested markets, buying NO as a maker, spread <= 2c, entry window 36h-3h before close. A fill is counted only when a trade printed strictly THROUGH our resting price with the taker on the opposite side, since at our own price we cannot know our queue position.

- **Fill rate: 56.0%**

- all markets (maker_lab's assumption): **+0.13c** [-1.31, +1.58] on n=2960
- would have filled: **-0.73c** [-2.79, +1.33] on n=1658
- would NOT have filled: **+1.29c** [-0.67, +3.25] on n=1301

**Adverse selection: +0.86c/contract.** This is the amount maker_lab overstates the maker case by, because it scores every market rather than only the ones a resting order would actually have caught.

No trade data for 1 markets; 0 API errors.

Research only. Nothing here places an order.
