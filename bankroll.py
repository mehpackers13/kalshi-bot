"""
BANKROLL TRACKER
================
Persists live and paper bankroll balances to data/bankroll.json.
The live balance is updated manually or via Kalshi API balance check.
Paper trades are simulated automatically.
"""

import json
import datetime
from pathlib import Path
from typing import Optional

import config
from logger import log

_DEFAULT = {
    "live":  {"balance": config.LIVE_BANKROLL_START,  "start": config.LIVE_BANKROLL_START,  "peak": config.LIVE_BANKROLL_START},
    "paper": {"balance": config.PAPER_BANKROLL_START, "start": config.PAPER_BANKROLL_START, "peak": config.PAPER_BANKROLL_START},
    "live_stopped":  False,
    "updated_at": "",
}


def load_bankroll() -> dict:
    config.DATA_DIR.mkdir(exist_ok=True)
    if config.BANKROLL_JSON.exists():
        try:
            return json.loads(config.BANKROLL_JSON.read_text())
        except Exception:
            pass
    return dict(_DEFAULT)


def save_bankroll(data: dict) -> None:
    config.DATA_DIR.mkdir(exist_ok=True)
    data["updated_at"] = datetime.datetime.utcnow().isoformat() + "Z"
    config.BANKROLL_JSON.write_text(json.dumps(data, indent=2))


def apply_paper_outcome(dollars_risked: float, won: bool, payout_per_dollar: float) -> None:
    """Update paper bankroll after a market resolves."""
    br = load_bankroll()
    if won:
        profit = dollars_risked * payout_per_dollar
        br["paper"]["balance"] += profit
    else:
        br["paper"]["balance"] -= dollars_risked
    br["paper"]["balance"] = round(br["paper"]["balance"], 2)
    br["paper"]["peak"]    = max(br["paper"]["peak"], br["paper"]["balance"])
    save_bankroll(br)


def sync_live_balance(api) -> Optional[float]:
    """
    Fetch live balance from Kalshi API and update bankroll.json.
    Returns new balance or None on failure.
    """
    balance = api.get_account_balance()
    if balance is None:
        return None
    br = load_bankroll()
    br["live"]["balance"] = balance
    br["live"]["peak"]    = max(br["live"]["peak"], balance)
    save_bankroll(br)
    return balance


def check_drawdown_stop() -> bool:
    """Returns True if live bankroll has hit the 20% drawdown stop."""
    br = load_bankroll()
    if br.get("live_stopped"):
        return True
    start   = br["live"]["start"]
    current = br["live"]["balance"]
    drawdown = (start - current) / start if start > 0 else 0
    if drawdown >= config.DRAWDOWN_STOP_PCT:
        br["live_stopped"] = True
        save_bankroll(br)
        log(f"DRAWDOWN STOP TRIGGERED: balance ${current:.2f} is "
            f"{drawdown:.1%} below start ${start:.2f}", "WARN")
        return True
    return False
