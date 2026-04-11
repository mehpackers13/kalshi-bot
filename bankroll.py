"""
BANKROLL TRACKER
================
Live balance is read directly from the Kalshi API on every scan —
no hardcoded starting amount. The drawdown stop is based on the
highest balance the bot has ever seen (peak), not a fixed starting number.

This means:
  • Deposits are picked up automatically on the next scan.
  • The drawdown stop adjusts upward as the account grows.
  • Nothing in config.py needs to change when you add money.

Drawdown rule: stop trading if live balance drops below
  peak * (1 - DRAWDOWN_STOP_PCT)   e.g. peak $200 -> stop at $100 (50%)

bankroll.json is committed to the repo after every scan so peak
history is preserved across GitHub Actions runs.
"""

import json
import datetime
from typing import Optional

import config
from logger import log


# ── Default skeleton (zeroes — populated on first API sync) ─────────────────────

def _fresh_bankroll() -> dict:
    return {
        "live": {
            "balance": 0.0,   # updated from Kalshi API every scan
            "peak":    0.0,   # highest balance ever seen — never decreases
        },
        "paper": {
            "balance": config.PAPER_BANKROLL_START,
            "peak":    config.PAPER_BANKROLL_START,
        },
        "live_stopped": False,
        "updated_at":   "",
    }


# ── IO helpers ───────────────────────────────────────────────────────────────────

def load_bankroll() -> dict:
    config.DATA_DIR.mkdir(exist_ok=True)
    if config.BANKROLL_JSON.exists():
        try:
            return json.loads(config.BANKROLL_JSON.read_text())
        except Exception:
            pass
    return _fresh_bankroll()


def save_bankroll(data: dict) -> None:
    config.DATA_DIR.mkdir(exist_ok=True)
    data["updated_at"] = datetime.datetime.utcnow().isoformat() + "Z"
    config.BANKROLL_JSON.write_text(json.dumps(data, indent=2))


# ── Live balance sync ────────────────────────────────────────────────────────────

def sync_live_balance(api) -> Optional[float]:
    """
    Fetch total portfolio value (cash + open positions) from Kalshi API.
    Using total value — not cash alone — prevents false drawdown triggers
    when money is locked in open positions.
    On first call (peak == 0) the value becomes the peak baseline.
    Returns total portfolio value, or None if API calls failed.
    """
    # Total value includes open position market value at current bid prices
    total = api.get_portfolio_total_value()
    if total is None:
        # Fallback to cash-only if portfolio call fails
        total = api.get_account_balance()
    if total is None:
        log("Could not read Kalshi portfolio value — using cached value", "WARN")
        return None

    br = load_bankroll()

    if br["live"]["peak"] == 0.0:
        br["live"]["peak"] = total
        log(f"Live bankroll initialised: ${total:.2f}  (peak baseline set, total portfolio)")
    elif total > br["live"]["peak"]:
        log(f"New peak portfolio value: ${total:.2f}  (was ${br['live']['peak']:.2f})")

    br["live"]["balance"] = round(total, 2)
    br["live"]["peak"]    = round(max(br["live"]["peak"], total), 2)
    save_bankroll(br)
    log(f"Portfolio value: ${total:.2f}  |  Peak ever: ${br['live']['peak']:.2f}")
    return total


# ── Drawdown stop ────────────────────────────────────────────────────────────────

def check_drawdown_stop() -> bool:
    """
    Returns True if trading should halt.
    Rule: stop when live balance < peak * (1 - DRAWDOWN_STOP_PCT)
    With DRAWDOWN_STOP_PCT = 0.50:  peak $100 -> stop below $50
    The threshold rises automatically as the account grows.
    """
    br = load_bankroll()

    if br.get("live_stopped"):
        return True

    peak    = br["live"]["peak"]
    current = br["live"]["balance"]

    # Wait for at least one real balance reading before enforcing
    if peak == 0.0 or current == 0.0:
        return False

    stop_at = round(peak * (1.0 - config.DRAWDOWN_STOP_PCT), 2)

    if current < stop_at:
        already_stopped = br.get("live_stopped", False)
        br["live_stopped"] = True
        save_bankroll(br)
        log(
            f"DRAWDOWN STOP: balance ${current:.2f} fell below "
            f"{config.DRAWDOWN_STOP_PCT:.0%}-from-peak threshold ${stop_at:.2f} "
            f"(peak was ${peak:.2f})",
            "WARN",
        )
        if not already_stopped:
            try:
                import auto_bettor
                auto_bettor._send_drawdown_alert(br)
            except Exception:
                pass
        return True

    return False


def reset_drawdown_stop() -> None:
    """Clear the drawdown stop flag so scanning resumes immediately."""
    br = load_bankroll()
    br["live_stopped"] = False
    save_bankroll(br)
    log("Drawdown stop cleared — scanning will resume on next run")


# ── Paper trading ────────────────────────────────────────────────────────────────

def apply_paper_outcome(dollars_risked: float, won: bool, payout_per_dollar: float) -> None:
    """Update paper bankroll after a simulated market resolves."""
    br = load_bankroll()
    if won:
        br["paper"]["balance"] = round(br["paper"]["balance"] + dollars_risked * payout_per_dollar, 2)
    else:
        br["paper"]["balance"] = round(br["paper"]["balance"] - dollars_risked, 2)
    br["paper"]["peak"] = round(max(br["paper"]["peak"], br["paper"]["balance"]), 2)
    save_bankroll(br)


# ── Convenience getters ──────────────────────────────────────────────────────────

def live_balance() -> float:
    return load_bankroll()["live"]["balance"]

def live_peak() -> float:
    return load_bankroll()["live"]["peak"]

def paper_balance() -> float:
    return load_bankroll()["paper"]["balance"]
