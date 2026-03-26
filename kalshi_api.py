"""
KALSHI API WRAPPER
==================
Thin wrapper around the official Kalshi REST API v2.
Handles authentication, token refresh, and all market data calls.
Docs: https://trading-api.kalshi.com/docs
"""

import time
import datetime
from typing import Optional
import requests

import config
from logger import log


class KalshiAPI:
    """Authenticated session for the Kalshi trading API."""

    BASE = config.KALSHI_BASE_URL

    def __init__(self):
        self._token: str = ""
        self._token_expiry: float = 0.0
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})

    # ── Authentication ──────────────────────────────────────────────────────────

    def login(self) -> bool:
        """Login and cache the JWT. Returns True on success."""
        if not config.KALSHI_EMAIL or not config.KALSHI_PASSWORD:
            log("No KALSHI_EMAIL / KALSHI_PASSWORD set — running in data-only mode", "WARN")
            return False
        try:
            resp = self._session.post(
                f"{self.BASE}/login",
                json={"email": config.KALSHI_EMAIL, "password": config.KALSHI_PASSWORD},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                self._token = data.get("token", "")
                if self._token:
                    self._session.headers["Authorization"] = f"Bearer {self._token}"
                    # Tokens last 24h; refresh after 20h to be safe
                    self._token_expiry = time.time() + 20 * 3600
                    log("Kalshi login OK ✅")
                    return True
            log(f"Kalshi login failed: HTTP {resp.status_code} — {resp.text[:200]}", "ERROR")
        except Exception as exc:
            log(f"Kalshi login error: {exc}", "ERROR")
        return False

    def _ensure_auth(self):
        if time.time() > self._token_expiry:
            self.login()

    def _get(self, path: str, params: dict = None, timeout: int = 15) -> Optional[dict]:
        self._ensure_auth()
        try:
            resp = self._session.get(
                f"{self.BASE}{path}",
                params=params or {},
                timeout=timeout,
            )
            if resp.status_code == 200:
                return resp.json()
            log(f"API GET {path} → HTTP {resp.status_code}", "WARN")
        except Exception as exc:
            log(f"API GET {path} error: {exc}", "WARN")
        return None

    # ── Market data ─────────────────────────────────────────────────────────────

    def get_markets(self, limit: int = 200, cursor: str = None,
                    status: str = "open", category: str = None) -> dict:
        """Fetch a page of markets. Returns {'markets': [...], 'cursor': ...}"""
        params = {"limit": limit, "status": status}
        if cursor:
            params["cursor"] = cursor
        if category:
            params["category"] = category
        data = self._get("/markets", params=params)
        return data or {"markets": [], "cursor": None}

    def get_all_open_markets(self) -> list:
        """Paginate through ALL open markets and return them as a flat list."""
        all_markets = []
        cursor = None
        pages = 0
        while pages < 50:   # hard cap to avoid runaway loops
            page = self.get_markets(limit=200, cursor=cursor, status="open")
            batch = page.get("markets", [])
            all_markets.extend(batch)
            cursor = page.get("cursor")
            pages += 1
            if not cursor or not batch:
                break
            time.sleep(0.3)   # polite rate limiting
        log(f"Fetched {len(all_markets)} open markets across {pages} pages")
        return all_markets

    def get_market(self, ticker: str) -> Optional[dict]:
        """Get full detail for a single market."""
        data = self._get(f"/markets/{ticker}")
        return data.get("market") if data else None

    def get_orderbook(self, ticker: str) -> Optional[dict]:
        """Get the current orderbook for a market."""
        data = self._get(f"/markets/{ticker}/orderbook")
        return data.get("orderbook") if data else None

    def get_market_history(self, ticker: str, limit: int = 100) -> list:
        """Get recent trade history for a market."""
        data = self._get(f"/markets/{ticker}/trades", params={"limit": limit})
        return (data or {}).get("trades", [])

    def get_account_balance(self) -> Optional[float]:
        """Return current cash balance in dollars (Kalshi stores in cents)."""
        data = self._get("/portfolio/balance")
        if data:
            cents = data.get("balance", 0)
            return round(cents / 100, 2)
        return None

    def get_portfolio_positions(self) -> list:
        """Return open positions."""
        data = self._get("/portfolio/positions", params={"limit": 200})
        return (data or {}).get("market_positions", [])

    def get_settled_markets(self, limit: int = 100) -> list:
        """Return recently settled markets (for outcome tracking)."""
        data = self._get("/markets", params={"status": "finalized", "limit": limit})
        return (data or {}).get("markets", [])


# ── Helpers ─────────────────────────────────────────────────────────────────────

def parse_market(raw: dict) -> Optional[dict]:
    """
    Normalise a raw Kalshi market dict into a clean standard format.
    Returns None if the market is missing essential fields.
    """
    try:
        ticker      = raw.get("ticker", "")
        title       = raw.get("title", "")
        category    = raw.get("category", "")
        subtitle    = raw.get("subtitle", "")

        # Prices are in cents (0–99). yes_ask is the cost to buy YES.
        yes_bid = int(raw.get("yes_bid", 0) or 0)
        yes_ask = int(raw.get("yes_ask", 0) or 0)

        if yes_ask <= 0 or yes_ask >= 100:
            return None

        # Mid-price as implied probability
        implied_prob = ((yes_bid + yes_ask) / 2) / 100.0

        # Volume: Kalshi reports volume in number of contracts
        volume       = int(raw.get("volume", 0) or 0)
        volume_24h   = int(raw.get("volume_24h", 0) or 0)
        open_interest = int(raw.get("open_interest", 0) or 0)

        # Dollar volume ≈ contracts × avg_price × $1/contract
        avg_price_cents = (yes_bid + yes_ask) / 2
        dollar_volume   = volume * (avg_price_cents / 100)

        # Close time
        close_time_str = raw.get("close_time") or raw.get("expiration_time", "")
        close_time = None
        hours_to_close = 999.0
        if close_time_str:
            try:
                close_time = datetime.datetime.fromisoformat(
                    close_time_str.replace("Z", "+00:00")
                )
                now = datetime.datetime.now(datetime.timezone.utc)
                hours_to_close = (close_time - now).total_seconds() / 3600
            except Exception:
                pass

        return {
            "ticker":          ticker,
            "title":           title,
            "subtitle":        subtitle,
            "category":        category,
            "yes_bid":         yes_bid,
            "yes_ask":         yes_ask,
            "implied_prob":    implied_prob,
            "volume":          volume,
            "volume_24h":      volume_24h,
            "open_interest":   open_interest,
            "dollar_volume":   dollar_volume,
            "close_time":      close_time_str,
            "hours_to_close":  hours_to_close,
            "result":          raw.get("result", ""),
            "status":          raw.get("status", ""),
        }
    except Exception:
        return None
