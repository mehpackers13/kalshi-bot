"""
KALSHI BOT — CONFIGURATION
===========================
Edit this file to customize the bot.
Secrets (credentials, Discord webhook) come from environment variables
set as GitHub Secrets — never put passwords in this file.
"""

import os

# ── Credentials (from GitHub Secrets / environment) ────────────────────────────
# Kalshi migrated to RSA API key auth in 2025.
# Get your API key at: kalshi.com/account/profile → API Keys
KALSHI_API_KEY_ID  = os.environ.get("KALSHI_API_KEY_ID", "")
KALSHI_PRIVATE_KEY = os.environ.get("KALSHI_PRIVATE_KEY", "")   # full PEM string

DISCORD_SIGNALS_WEBHOOK = os.environ.get("DISCORD_SIGNALS_WEBHOOK", "")
DISCORD_HEALTH_WEBHOOK  = os.environ.get("DISCORD_HEALTH_WEBHOOK", "")

# ── Bankroll ────────────────────────────────────────────────────────────────────
LIVE_BANKROLL_START   = 100.0    # dollars — your real Kalshi balance
PAPER_BANKROLL_START  = 1000.0   # dollars — simulated parallel portfolio

# ── Edge & Filters ──────────────────────────────────────────────────────────────
MIN_EDGE_PCT          = 8.0      # minimum edge % to alert (below = silence)
MIN_VOLUME_DOLLARS    = 5000     # Discord alert threshold — only alert on liquid markets
DISCOVERY_VOLUME_DOLLARS = 500   # diagnostic scan floor — surfaces markets approaching liquidity
MIN_IMPLIED_PROB      = 0.15     # skip YES probability below 15%
MAX_IMPLIED_PROB      = 0.85     # skip YES probability above 85%
MIN_HOURS_TO_CLOSE    = 2.0      # skip markets closing in under 2 hours

# ── Kelly Bet Sizing ────────────────────────────────────────────────────────────
# Fractional Kelly — keeps sizing conservative. Never bet the full Kelly amount.
KELLY_FRACTION        = 0.25     # use 25% of Kelly recommendation

# Hard caps by edge bucket (% of LIVE bankroll per bet)
BET_SIZE_SMALL_MAX    = 0.02     # edge  8–15%  → max 2% of bankroll
BET_SIZE_MEDIUM_MAX   = 0.04     # edge 15–25%  → max 4% of bankroll
BET_SIZE_STRONG_MAX   = 0.05     # edge 25%+    → max 5% of bankroll

# ── Risk Brakes ─────────────────────────────────────────────────────────────────
DRAWDOWN_STOP_PCT     = 0.20     # stop trading if live bankroll drops 20%

# ── Scanning ────────────────────────────────────────────────────────────────────
SCAN_INTERVAL_MINUTES = 30

# Market categories Kalshi uses — we scan all of them
KALSHI_CATEGORIES = [
    "Economics", "Politics", "Weather", "Sports",
    "Entertainment", "Financials", "Technology", "Health",
    "Crypto", "Climate", "Science",
]

# Categories where our probability models are reliable enough to trade
MODELABLE_CATEGORIES = {
    "Financials",      # stock / index price targets
    "Crypto",          # crypto price targets
    "Economics",       # CPI, Fed rate, unemployment, GDP
    "Weather",         # temperature / precipitation (climatological base rates)
}

# ── Kalshi API ──────────────────────────────────────────────────────────────────
KALSHI_BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"

# ── File paths ──────────────────────────────────────────────────────────────────
from pathlib import Path
BASE_DIR          = Path(__file__).parent
DATA_DIR          = BASE_DIR / "data"
DOCS_DIR          = BASE_DIR / "docs"
OUTCOMES_CSV      = BASE_DIR / "outcomes.csv"
BANKROLL_JSON     = DATA_DIR / "bankroll.json"
MODELS_JSON       = DATA_DIR / "models.json"
BOT_LOG           = BASE_DIR / "bot.log"
AI_SUGGESTIONS    = DATA_DIR / "ai_suggestions.json"
