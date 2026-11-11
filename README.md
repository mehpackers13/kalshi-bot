# Kalshi Bot 🎯

A self-improving Kalshi prediction market trading bot. Disciplined, selective, and honest — a week with zero alerts is a success, not a failure.

## What it does

- Scans ALL Kalshi markets every 30 minutes, 24/7 via GitHub Actions (no Mac needed)
- Detects edges ≥8% using probability models for Crypto, Financials, and Economics markets
- Sizes bets with fractional Kelly Criterion — max 5% of bankroll per trade
- Sends Discord alerts to `#kalshi-signals` with full reasoning
- Runs a parallel $1,000 paper trading portfolio for comparison
- Automatically resolves outcomes from Kalshi's settled market data
- Self-improves every morning at 8am ET — adjusts model confidence based on actual hit rates
- Optional Claude AI brain for pattern analysis (needs ANTHROPIC_API_KEY)
- Weekly Sunday review sent to Discord

## What this bot does right now

**Short version: it is paper-trading only. No money moves.** The bot watches Kalshi, writes down
"pretend bets" under several different rules, and tracks how each rule would have done. Your real
Kalshi account (cash plus the 5 long-dated positions) is not touched by any of this.

- **Alerts** are model-based suggestions sent to `#kalshi-signals`. They are dry-run: nothing is placed.
  The morning report counts each market once (not once per daily re-alert), net of Kalshi fees.
  The audited record is 26 wins out of 76 resolved markets, roughly -38 units.
- **Paper rules** each pick markets by a simple idea (for example weather tails, sportsbook-vs-Kalshi gaps).
  Every pretend entry pays the real ask (or 1 minus the bid for NO) plus the taker fee, so the results
  include the cost of the spread.
- **Crypto paper** runs the same idea on on-chain/DEX data, also pretend only.
- **Lab candidates** come from the weekly backtest. They are in-sample only: they looked good on past
  data and have not been tested going forward, so they are not proof of anything.

### How to read the scoreboard (daily, in `#bot-health`)

| Column | Meaning |
|---|---|
| status | `active` = still being tested, `candidate` = passed the gate, `killed` = switched off |
| ev (settled/events) | settled pretend bets / distinct events. Several strikes on one event count as one |
| net¢ | average profit per event in cents, after fees. Positive is good |
| 95% CI | the plausible range for that average. If it is entirely above 0, the result is unlikely to be luck |
| CLV¢ | closing-line value: did we buy at a better price than where the market ended up? Positive means a real edge in timing |
| open | pretend bets not yet settled |

**Candidate** means: at least 30 events, average at least +1¢, the confidence interval's low end above 0,
and both halves of the history positive. **Killed** means the rule lost too convincingly to keep
(30+ events with the interval's top below 0, or 60+ events with negative net and negative CLV).
Nothing is called proven with fewer than 30 events.

### How a rule would reach real money

1. 30 or more events, net at least +1¢, 95% interval above 0, and both halves of the history positive.
2. It shows up as a **candidate** on the scoreboard and in `#kalshi-signals`.
3. Then it is Mike's decision. The bot never promotes a rule to real money on its own.

## Quick Start

### 1. Add GitHub Secrets

Go to your repo → Settings → Secrets and variables → Actions → New repository secret:

| Secret | Value |
|--------|-------|
| `KALSHI_EMAIL` | Your Kalshi login email |
| `KALSHI_PASSWORD` | Your Kalshi login password |
| `DISCORD_SIGNALS_WEBHOOK` | Webhook URL for `#kalshi-signals` channel |
| `DISCORD_HEALTH_WEBHOOK` | Webhook URL for `#bot-health` channel |
| `ANTHROPIC_API_KEY` | *(Optional)* Claude API key for AI brain |

### 2. Set up Discord webhooks (2 minutes each)

1. Open your Discord server → right-click a channel → Edit Channel
2. Go to Integrations → Webhooks → New Webhook
3. Copy the webhook URL → paste into GitHub Secrets

Create two channels: `#kalshi-signals` and `#bot-health`

### 3. Enable GitHub Pages

Repo → Settings → Pages → Source: **GitHub Actions**

Your dashboard will be live at: `https://mehpackers13.github.io/kalshi-bot/`

### 4. Trigger your first scan

Repo → Actions → Kalshi Scan → Run workflow

## Risk Management Rules (hardcoded)

- ✅ Minimum edge: **8%**
- ✅ Minimum volume: **$5,000**
- ✅ Implied probability: **15%–85%** only
- ✅ Minimum time to close: **2 hours**
- ✅ Max bet: **5% of live bankroll**
- 🛑 **20% drawdown stop** — bot alerts you and halts live suggestions

## How the self-improvement works

1. Every alert is logged to `outcomes.csv`
2. Kalshi's API is polled to auto-resolve settled markets (win/loss)
3. Each morning the bot calculates hit rates by category and edge size
4. If a category hit rate > 65% → model confidence goes up
5. If a category hit rate < 45% → model confidence goes down
6. Every change is logged to `model_changes.log` with a reason

## Current probability models

| Category | Model | Reliability |
|----------|-------|-------------|
| Crypto | Log-normal vol model using live prices | ★★★★☆ |
| Financials | Log-normal vol model using live prices | ★★★★☆ |
| Economics (Fed) | Fed Funds futures implied rate | ★★★☆☆ |
| Economics (CPI) | Treasury yield trend proxy | ★★☆☆☆ |
| Weather | Climatological base rates | ★★☆☆☆ |
| Sports/Politics/Entertainment | **Not modelled — bot stays silent** | — |

## File structure

```
kalshi-bot/
├── config.py              # All settings — edit this
├── kalshi_api.py          # Official Kalshi API wrapper
├── probability_models.py  # Category-specific probability calculators
├── edge_calculator.py     # Edge detection + confidence scoring
├── kelly.py               # Fractional Kelly bet sizing
├── bankroll.py            # Live + paper bankroll tracking
├── outcomes.py            # Alert logging + auto-resolution
├── scanner.py             # Main scan loop
├── self_improve.py        # Morning analysis + model adjustment
├── morning_report.py      # Daily briefing + weekly review
├── discord_alerts.py      # Discord message formatting
├── generate_data.py       # Dashboard data generator
├── run_scan.py            # GitHub Actions entry point (scan)
├── run_morning.py         # GitHub Actions entry point (morning)
├── run_weekly.py          # GitHub Actions entry point (weekly)
├── outcomes.csv           # Every alert + outcome
├── data/
│   ├── bankroll.json      # Live + paper balances
│   ├── models.json        # Self-improving model parameters
│   └── ai_suggestions.json
└── docs/
    ├── index.html         # Dashboard
    └── data.json          # Dashboard data (auto-generated)
```

## Rating outcomes manually

Open `outcomes.csv` → find the row → set `outcome` to `1` (correct) or `0` (wrong).
The bot auto-resolves most markets from Kalshi's API. Manual rating is only needed
if the auto-resolution misses something.

## Growing $100 into real money

The math: at a 60% hit rate on 8%+ edges with proper Kelly sizing, the expectation
is strongly positive. But it takes patience — the bot will stay silent for days at a
time rather than fire a weak signal. That discipline is the edge.
