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
# Live bankroll start is no longer hardcoded — the bot reads your actual
# Kalshi balance via the API on every scan and adjusts automatically.
# Deposits are picked up with no config changes needed.
PAPER_BANKROLL_START  = 1000.0   # simulated paper-trading starting balance

# ── Edge & Filters ──────────────────────────────────────────────────────────────
MIN_EDGE_PCT          = 8.0      # minimum edge % to alert (below = silence)
MIN_VOLUME_DOLLARS    = 5000     # Discord alert threshold — only alert on liquid markets
DISCOVERY_VOLUME_DOLLARS = 500   # diagnostic scan floor — surfaces markets approaching liquidity
MIN_IMPLIED_PROB      = 0.05     # skip YES probability below 5% (allow long-shots with real volume)
MAX_IMPLIED_PROB      = 0.95     # skip YES probability above 95% (near-certain = no edge)
MIN_HOURS_TO_CLOSE    = 2.0      # skip markets closing in under 2 hours

# ── Kelly Bet Sizing ────────────────────────────────────────────────────────────
# Fractional Kelly — keeps sizing conservative. Never bet the full Kelly amount.
KELLY_FRACTION        = 0.25     # 25% Kelly for Discord alert sizing (unchanged)
AUTO_BET_KELLY_FRACTION = 0.50   # 50% Kelly for auto-placed bets
AUTO_BET_MAX_PCT      = 0.05     # hard cap — never >5% of live balance per auto-bet

# Hard caps by edge bucket (% of LIVE bankroll per bet)
BET_SIZE_SMALL_MAX    = 0.02     # edge  8–15%  → max 2% of bankroll
BET_SIZE_MEDIUM_MAX   = 0.04     # edge 15–25%  → max 4% of bankroll
BET_SIZE_STRONG_MAX   = 0.05     # edge 25%+    → max 5% of bankroll

# ── Risk Brakes ─────────────────────────────────────────────────────────────────
DRAWDOWN_STOP_PCT     = 0.40     # pause auto-betting if balance drops 40% below peak

# ── Auto-Betting Engine ─────────────────────────────────────────────────────────
# Set DRY_RUN = True to log what the bot WOULD bet without placing real orders.
# Flip to False to go live.  Default: True (safe first-run mode).
DRY_RUN               = False
MAX_AUTO_BETS_PER_HOUR = 3        # rate limit — prevents runaway loops

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
BETS_PLACED_CSV   = BASE_DIR / "bets_placed.csv"
BANKROLL_JSON     = DATA_DIR / "bankroll.json"
MODELS_JSON       = DATA_DIR / "models.json"
BOT_LOG           = BASE_DIR / "bot.log"
AI_SUGGESTIONS    = DATA_DIR / "ai_suggestions.json"
