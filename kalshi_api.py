"""
KALSHI API WRAPPER
==================
Kalshi migrated from email/password to RSA API key authentication in 2025.
Markets endpoint is public (no auth needed for scanning).
Portfolio endpoints require RSA-signed headers.

New API field names (changed from v1):
  yes_bid / yes_ask (cents)  →  yes_bid_dollars / yes_ask_dollars (dollar strings)
  volume (int)                →  volume_fp (float string)
  category on market          →  category on event (requires separate /events fetch)

Setup:
  1. Go to kalshi.com/account/profile → API Keys → Create New API Key
  2. Add GitHub Secrets: KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY (full PEM)

Docs: https://docs.kalshi.com/getting_started/api_keys
"""

import base64
import time
import datetime
from typing import Optional

import requests

import config
from logger import log


class KalshiAPI:

    BASE = config.KALSHI_BASE_URL
    _event_category_cache: dict = {}   # event_ticker → category string

    def __init__(self):
        self._key_id      = config.KALSHI_API_KEY_ID
        self._private_key = config.KALSHI_PRIVATE_KEY.strip()
        self._session     = requests.Session()
        self._session.headers.update({"Accept": "application/json"})
        self._authenticated = False

    # ── RSA signing ──────────────────────────────────────────────────────────────

    def _sign_request(self, method: str, path: str) -> dict:
        """Return auth headers for a signed request, or {} if no key configured."""
        if not self._key_id or not self._private_key:
            return {}
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding

            ts_ms = str(int(time.time() * 1000))
            # Kalshi requires the FULL path in the signature, including the
            # /trade-api/v2 prefix — NOT just the endpoint path fragment.
            # e.g. sign "/trade-api/v2/portfolio/balance", not "/portfolio/balance"
            endpoint  = path.split("?")[0]
            sign_path = "/trade-api/v2" + endpoint
            message   = (ts_ms + method.upper() + sign_path).encode("utf-8")

            # Normalise PEM key stored as a single-line string in env vars.
            # GitHub Secrets preserve newlines, but some shells collapse them.
            pem = self._private_key
            if "\n" not in pem:
                # Detect header type and re-wrap with line breaks
                if "RSA PRIVATE KEY" in pem:
                    header, footer = "-----BEGIN RSA PRIVATE KEY-----", "-----END RSA PRIVATE KEY-----"
                else:
                    header, footer = "-----BEGIN PRIVATE KEY-----", "-----END PRIVATE KEY-----"
                body = pem.replace(header, "").replace(footer, "").strip()
                pem  = header + "\n" + "\n".join(body[i:i+64] for i in range(0, len(body), 64)) + "\n" + footer

            private_key = serialization.load_pem_private_key(
                pem.encode(), password=None
            )

            # Kalshi requires RSA-PSS with SHA-256 (NOT PKCS1v15)
            sig     = private_key.sign(
                message,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH,
                ),
                hashes.SHA256(),
            )
            sig_b64 = base64.b64encode(sig).decode()

            return {
                "KALSHI-ACCESS-KEY":       self._key_id,
                "KALSHI-ACCESS-TIMESTAMP": ts_ms,
                "KALSHI-ACCESS-SIGNATURE": sig_b64,
            }
        except Exception as exc:
            log(f"RSA signing failed: {exc}", "WARN")
            return {}

    # ── HTTP helpers ──────────────────────────────────────────────────────────────

    def _post(self, path: str, payload: dict, timeout: int = 15) -> dict:
        """Authenticated POST — used for order placement."""
        import json as _json
        headers = self._sign_request("POST", path)
        headers["Content-Type"] = "application/json"
        resp = self._session.post(
            f"{self.BASE}{path}",
            headers=headers,
            data=_json.dumps(payload),
            timeout=timeout,
        )
        if resp.status_code not in (200, 201):
            raise Exception(
                f"Kalshi POST {path} → HTTP {resp.status_code}: {resp.text[:300]}"
            )
        return resp.json()

    def place_order(self, ticker: str, side: str, count: int,
                    yes_price: int) -> dict:
        """
        Place a limit order on Kalshi.
          side:      "yes" or "no"
          yes_price: price of the YES side in cents (1–99)
          count:     number of contracts to buy
        Returns the full API response dict including order_id.
        """
        import uuid
        payload = {
            "ticker":          ticker,
            "side":            side,
            "action":          "buy",
            "count":           count,
            "type":            "limit",
            "yes_price":       yes_price,
            "client_order_id": str(uuid.uuid4()),
        }
        return self._post("/portfolio/orders", payload)

    def _get(self, path: str, params: dict = None, timeout: int = 15) -> Optional[dict]:
        qs = ""
        if params:
            from urllib.parse import urlencode
            qs = "?" + urlencode(params)
        headers = self._sign_request("GET", path)
        try:
            resp = self._session.get(
                f"{self.BASE}{path}{qs}",
                headers=headers,
                timeout=timeout,
            )
            if resp.status_code == 200:
                return resp.json()
            log(f"API GET {path} → HTTP {resp.status_code}", "WARN")
        except Exception as exc:
            log(f"API GET {path} error: {exc}", "WARN")
        return None

    # ── Authentication check ──────────────────────────────────────────────────────

    def login(self) -> bool:
        """Validate credentials with a lightweight authenticated call."""
        if not self._key_id or not self._private_key:
            log("No KALSHI_API_KEY_ID / KALSHI_PRIVATE_KEY — scanning public markets only", "WARN")
            return False
        data = self._get("/portfolio/balance")
        if data is not None:
            bal = data.get("balance", 0) / 100
            log(f"Kalshi API key auth OK ✅  balance: ${bal:.2f}")
            self._authenticated = True
            return True
        log("Kalshi API key auth FAILED — check KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY", "ERROR")
        return False

    # ── Event category cache ──────────────────────────────────────────────────────

    def _build_event_category_cache(self, limit_pages: int = 10) -> None:
        """
        Fetch events in bulk and cache event_ticker → category.
        Call this once before a full market scan.
        """
        cursor = None
        fetched = 0
        for _ in range(limit_pages):
            params = {"limit": 200, "status": "open"}
            if cursor:
                params["cursor"] = cursor
            data = self._get("/events", params=params)
            if not data:
                break
            events = data.get("events", [])
            for ev in events:
                eticker  = ev.get("event_ticker", "")
                category = ev.get("category", "")
                if eticker and category:
                    self._event_category_cache[eticker] = category
            fetched += len(events)
            cursor = data.get("cursor")
            if not cursor or not events:
                break
            time.sleep(0.2)
        log(f"Event category cache built: {len(self._event_category_cache)} events from {fetched} fetched")

    def _category_for_market(self, raw: dict) -> str:
        """
        Look up category from the event cache, or infer from ticker prefix.
        """
        event_ticker = raw.get("event_ticker", "")
        if event_ticker in self._event_category_cache:
            return self._event_category_cache[event_ticker]

        # Fallback: infer from ticker prefix patterns
        ticker = raw.get("ticker", "").upper()
        prefix_map = {
            "KXBTC": "Crypto",   "KXETH": "Crypto",   "KXSOL": "Crypto",
            "KXXRP": "Crypto",   "KXDOGE": "Crypto",  "KXBNB": "Crypto",
            "KXSPY": "Financials","KXQQQ": "Financials","KXNVDA": "Financials",
            "KXAAPL": "Financials","KXTSLA": "Financials","KXGOOG": "Financials",
            "KXGOLD": "Financials","KXOIL": "Financials",
            "KXCPI": "Economics", "KXFED": "Economics", "KXFOMC": "Economics",
            "KXUNEMPLOYMENT": "Economics", "KXGDP": "Economics", "KXPCE": "Economics",
            "KXNBA": "Sports",   "KXNFL": "Sports",   "KXMLB": "Sports",
            "KXNHL": "Sports",   "KXNCAA": "Sports",  "KXSOCCER": "Sports",
            "KXWEATHER": "Weather", "KXTEMP": "Weather",
        }
        for prefix, cat in prefix_map.items():
            if ticker.startswith(prefix):
                return cat
        return ""

    # ── Markets ───────────────────────────────────────────────────────────────────

    def get_markets(self, limit: int = 200, cursor: str = None,
                    status: str = "open") -> dict:
        params = {"limit": limit, "status": status}
        if cursor:
            params["cursor"] = cursor
        data = self._get("/markets", params=params)
        return data or {"markets": [], "cursor": None}

    def get_all_open_markets(self) -> list:
        """
        Fetch all real prediction markets via the /events endpoint.
        The /markets endpoint returns only KXMVE parlay markets (zero liquidity).
        Real markets (crypto, economics, politics, weather) are only accessible
        via /events?with_nested_markets=true.
        Category is populated from the parent event.
        """
        all_markets = []
        cursor = None
        pages  = 0
        while pages < 50:
            params = {"limit": 200, "status": "open", "with_nested_markets": "true"}
            if cursor:
                params["cursor"] = cursor
            data = self._get("/events", params=params)
            if not data:
                break
            events = data.get("events", [])
            cursor  = data.get("cursor")
            pages  += 1

            for event in events:
                category = event.get("category", "")
                for m in event.get("markets", []):
                    # Propagate event category to each market
                    if not m.get("category"):
                        m["category"] = category
                    all_markets.append(m)

            if not cursor or not events:
                break
            time.sleep(0.25)

        log(f"Fetched {len(all_markets)} open markets via events endpoint across {pages} pages")
        return all_markets

    def get_settled_markets(self, limit: int = 100) -> list:
        data = self._get("/markets", params={"status": "finalized", "limit": limit})
        return (data or {}).get("markets", [])

    # ── Portfolio (authenticated) ─────────────────────────────────────────────────

    def get_account_balance(self) -> Optional[float]:
        data = self._get("/portfolio/balance")
        return round(data.get("balance", 0) / 100, 2) if data else None

    def get_portfolio_positions(self) -> list:
        data = self._get("/portfolio/positions", params={"limit": 200})
        return (data or {}).get("market_positions", [])


# ── Market parser ─────────────────────────────────────────────────────────────────

def parse_market(raw: dict) -> Optional[dict]:
    """
    Normalise a raw Kalshi API v2 market into a clean standard format.
    Handles the new dollar-string field names (yes_ask_dollars, volume_fp etc.)
    """
    try:
        ticker   = raw.get("ticker", "")
        title    = raw.get("title", "") or raw.get("yes_sub_title", "")
        category = raw.get("category", "")
        subtitle = raw.get("yes_sub_title", "")

        # Price normalisation: Kalshi v2 uses integers in cents (0–99).
        # Some responses also include *_dollars (0.00–1.00 strings).
        # Detect which format and always produce an integer in cents.
        def _to_cents(raw_val) -> int:
            if raw_val is None:
                return 0
            val = float(raw_val)
            # Dollar format: 0.0–1.0 → multiply; Cent format: 1–99 → use directly
            return int(round(val * 100)) if val <= 1.0 else int(round(val))

        yes_bid = _to_cents(
            raw.get("yes_bid_dollars") if raw.get("yes_bid_dollars") is not None
            else raw.get("yes_bid")
        )
        yes_ask = _to_cents(
            raw.get("yes_ask_dollars") if raw.get("yes_ask_dollars") is not None
            else raw.get("yes_ask")
        )

        # Filter out markets with no meaningful price
        if yes_ask <= 0 or yes_ask >= 100:
            return None
        if yes_bid < 0:
            return None

        implied_prob = ((yes_bid + yes_ask) / 2) / 100.0

        # Volume: new API uses volume_fp (float string)
        vol_raw   = raw.get("volume_fp") or raw.get("volume", 0)
        volume    = float(vol_raw) if vol_raw else 0.0

        vol24_raw = raw.get("volume_24h_fp") or raw.get("volume_24h", 0)
        volume_24h = float(vol24_raw) if vol24_raw else 0.0

        oi_raw = raw.get("open_interest_fp") or raw.get("open_interest", 0)
        open_interest = float(oi_raw) if oi_raw else 0.0

        # Dollar volume: use liquidity_dollars if available, else estimate
        liq_raw = raw.get("liquidity_dollars")
        if liq_raw and float(liq_raw) > 0:
            dollar_volume = float(liq_raw)
        else:
            avg_price = (yes_bid + yes_ask) / 2 / 100.0
            dollar_volume = volume * avg_price

        # Close time
        close_time_str = raw.get("close_time") or raw.get("expiration_time", "")
        hours_to_close = 999.0
        if close_time_str:
            try:
                close_dt = datetime.datetime.fromisoformat(
                    close_time_str.replace("Z", "+00:00")
                )
                now = datetime.datetime.now(datetime.timezone.utc)
                hours_to_close = (close_dt - now).total_seconds() / 3600
            except Exception:
                pass

        # Skip already-expired or settled markets
        if hours_to_close < 0:
            return None

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
            "status":          raw.get("status", "active"),
        }
    except Exception:
        return None
