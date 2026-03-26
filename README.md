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
