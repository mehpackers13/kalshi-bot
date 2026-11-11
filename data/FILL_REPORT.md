# Fill Lab — 2026-11-11T20:54:22Z

Measures the one number maker_lab.py assumes: whether a resting order fills, and whether filling means you were wrong.

120 harvested markets, buying YES as a maker, spread <= 2c, entry window 36h-3h before close. A fill is counted only when a trade printed strictly THROUGH our resting price with the taker on the opposite side, since at our own price we cannot know our queue position.

- **Fill rate: 44.9%**

- all markets (maker_lab's assumption): **-1.82c** [-9.11, +5.46] on n=107
- would have filled: **-8.46c** [-20.84, +3.92] on n=48
- would NOT have filled: **+3.57c** [-4.81, +11.96] on n=59

**Adverse selection: +6.64c/contract.** This is the amount maker_lab overstates the maker case by, because it scores every market rather than only the ones a resting order would actually have caught.

No trade data for 0 markets; 0 API errors.

Research only. Nothing here places an order.
