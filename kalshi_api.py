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
import json
import os
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

    @staticmethod
    def build_order_v2_payload(ticker: str, action: str, side: str, count: int,
                               price_cents: int, time_in_force: str = "immediate_or_cancel",
                               post_only: bool = False, client_order_id: str = None) -> dict:
        """Pure mapping to the V2 body (no network). Book is YES-only:
          (buy,yes,p)->bid@p  (buy,no,q)->ask@1-q  (sell,yes,p)->ask@p  (sell,no,q)->bid@1-q
        """
        import uuid
        action, side = action.lower(), side.lower()
        if action not in ("buy", "sell") or side not in ("yes", "no"):
            raise ValueError(f"bad action/side: {action}/{side}")
        price_cents = int(price_cents)
        if not 1 <= price_cents <= 99:
            raise ValueError(f"price_cents out of range: {price_cents}")
        if int(count) < 1:
            raise ValueError("count must be >= 1")
        if (action, side) in (("buy", "yes"), ("sell", "no")):
            book_side = "bid"
        else:
            book_side = "ask"
        yes_cents = price_cents if side == "yes" else 100 - price_cents
        body = {
            "ticker":        ticker,
            "side":          book_side,
            "count":         str(int(count)),
            "price":         "%.2f" % (yes_cents / 100.0),
            "time_in_force": time_in_force,
            "self_trade_prevention_type": "taker_at_cross",
            "client_order_id": client_order_id or str(uuid.uuid4()),
        }
        if post_only:
            body["post_only"] = True
        return body

    def place_order_v2(self, ticker: str, action: str, side: str, count: int,
                       price_cents: int, time_in_force: str = "immediate_or_cancel",
                       post_only: bool = False) -> dict:
        """V2 order (POST /portfolio/events/orders). price_cents is the price of
        the leg being traded (the NO price for side='no')."""
        if not getattr(config, "ORDERS_ENABLED", False):
            raise RuntimeError("orders disabled by config.ORDERS_ENABLED")
        payload = self.build_order_v2_payload(ticker, action, side, count,
                                              price_cents, time_in_force, post_only)
        return self._post("/portfolio/events/orders", payload)

    def place_order(self, ticker: str, side: str, count: int,
                    yes_price: int) -> dict:
        """Legacy signature: buy `side`; yes_price is the YES-side price in cents."""
        px = yes_price if side.lower() == "yes" else 100 - yes_price
        return self.place_order_v2(ticker, "buy", side, count, px)

    def create_combo_market(self, collection_ticker: str, legs: list) -> dict:
        """
        Create a Kalshi multi-leg parlay market inside the given collection.
        Kalshi charges 10 tokens per creation; limit is 5000/week.

        legs: list of {market_ticker, event_ticker, side}  (side = 'yes' or 'no')
        Returns the API response — the key field is `market_ticker`, which is
        the newly-created combo you then place a normal order against.
        """
        payload = {
            "selected_markets":    [
                {"market_ticker": l["market_ticker"],
                 "event_ticker":  l["event_ticker"],
                 "side":          l["side"]}
                for l in legs
            ],
            "with_market_payload": True,
        }
        return self._post(f"/multivariate_event_collections/{collection_ticker}", payload)

    def place_parlay(self, collection_ticker: str, legs: list,
                     count: int, max_price_cents: int = 99) -> dict:
        """
        Convenience: create the combo market if it doesn't exist, then place
        a YES limit order against it at or below max_price_cents.

        Returns {combo_ticker, order_id, status}.
        """
        combo = self.create_combo_market(collection_ticker, legs)
        combo_ticker = combo.get("market_ticker")
        if not combo_ticker:
            raise Exception(f"combo creation returned no market_ticker: {combo}")
        # Buy YES on the combo (hitting the ask up to max_price_cents)
        order = self.place_order(
            ticker    = combo_ticker,
            side      = "yes",
            count     = count,
            yes_price = min(max_price_cents, 99),
        )
        return {
            "combo_ticker": combo_ticker,
            "order_id":     (order.get("order") or {}).get("order_id"),
            "status":       (order.get("order") or {}).get("status"),
            "legs":         legs,
        }

    def list_combo_collections(self, limit: int = 100, pages: int = 1) -> list:
        """List available multivariate_event_collections so we can discover
        valid collection_tickers to parlay inside. Needed for the pairing
        logic to know which legs CAN be combined on Kalshi."""
        out, cursor = [], None
        for _ in range(max(1, pages)):
            params = {"limit": limit}
            if cursor:
                params["cursor"] = cursor
            data = self._get("/multivariate_event_collections", params=params)
            if not data:
                break
            batch = (data.get("collections") or data.get("multivariate_event_collections") or [])
            out.extend(batch)
            cursor = data.get("cursor")
            if not cursor or not batch:
                break
            time.sleep(0.2)
        return out

    def _get(self, path: str, params: dict = None, timeout: int = 15) -> Optional[dict]:
        qs = ""
        if params:
            from urllib.parse import urlencode
            qs = "?" + urlencode(params)
        # Kalshi rate-limits bursts (HTTP 429). Back off and retry rather than
        # treating the failure as "no data", which once made open positions
        # look worth $0 for a scan.
        for wait in (0, 2, 4, 8):
            if wait:
                time.sleep(wait)
            headers = self._sign_request("GET", path)
            try:
                resp = self._session.get(
                    f"{self.BASE}{path}{qs}",
                    headers=headers,
                    timeout=timeout,
                )
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code == 429:
                    continue
                self._warn_once(path, f"API GET {path} → HTTP {resp.status_code}")
                return None
            except Exception as exc:
                self._warn_once(path, f"API GET {path} error: {exc}")
                return None
        self._warn_once(path, f"API GET {path} → still rate-limited after retries")
        return None

    _warned_paths: set = set()

    @classmethod
    def _warn_once(cls, path: str, msg: str) -> None:
        """Log a repeated GET failure at most once per path per scan."""
        if path in cls._warned_paths:
            return
        cls._warned_paths.add(path)
        log(msg, "WARN")

    @classmethod
    def reset_warnings(cls) -> None:
        cls._warned_paths.clear()

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

    # ── Series -> category map ───────────────────────────────────────────────────

    _SERIES_CATS_FILE = config.DATA_DIR / "series_categories.json"
    _SERIES_TTL = 24 * 3600
    _series_cat_cache: dict = {}
    CATEGORY_LIST = ["Sports", "Crypto", "Financials", "Climate and Weather",
                     "Economics", "Commodities", "Companies", "Politics",
                     "Entertainment", "Elections", "Science and Technology",
                     "Health", "World", "Mentions"]

    def get_series_categories(self) -> dict:
        """series_ticker -> category. GET /series (no params) returns every
        series in one page (~16k, ~20MB); falls back to per-category calls.
        Cached in-process and in data/series_categories.json for 24h."""
        cls = KalshiAPI
        if cls._series_cat_cache:
            return cls._series_cat_cache
        try:
            if cls._SERIES_CATS_FILE.exists():
                blob = json.loads(cls._SERIES_CATS_FILE.read_text())
                if time.time() - float(blob.get("ts", 0)) < cls._SERIES_TTL and blob.get("map"):
                    cls._series_cat_cache = blob["map"]
                    return cls._series_cat_cache
        except Exception as exc:
            log(f"series_categories cache read failed: {exc}", "WARN")

        mapping = {}
        data = self._get("/series", timeout=60)
        rows = (data or {}).get("series") or []
        for r in rows:
            if r.get("ticker") and r.get("category"):
                mapping[r["ticker"]] = r["category"]
        if len(mapping) < 500:   # unfiltered call did not return the universe
            log("GET /series (no params) gave %d rows; falling back to per-category" % len(mapping), "WARN")
            for cat in cls.CATEGORY_LIST:
                d = self._get("/series", params={"category": cat}, timeout=60)
                for r in (d or {}).get("series") or []:
                    if r.get("ticker"):
                        mapping[r["ticker"]] = r.get("category") or cat
                time.sleep(0.2)
        if mapping:
            cls._series_cat_cache = mapping
            try:
                cls._SERIES_CATS_FILE.parent.mkdir(exist_ok=True)
                cls._SERIES_CATS_FILE.write_text(json.dumps({"ts": time.time(), "map": mapping},
                                                            separators=(",", ":")))
            except Exception as exc:
                log(f"series_categories cache write failed: {exc}", "WARN")
        return mapping

    def get_all_open_markets(self) -> list:
        """Open markets closing between SCAN_MIN_HOURS and SCAN_MAX_DAYS, via the
        /markets close-time window. Skips KXMVE combos, attaches category from the
        series map. Falls back to the events feed if fewer than 500 come back."""
        KalshiAPI.reset_warnings()
        cats = self.get_series_categories()
        now = int(time.time())
        lo = now + int(config.SCAN_MIN_HOURS * 3600)
        hi = now + int(config.SCAN_MAX_DAYS * 86400)
        # /markets pages come back newest-close-first, so one big window hits the
        # page cap before reaching the near-dated (liquid) markets. Slice the
        # window and fetch near slices first; the far end is what gets truncated.
        edges = [lo] + [now + int(h * 3600) for h in (24, 72, 168, 336, 720)] + [hi]
        edges = sorted(set(e for e in edges if lo <= e <= hi))
        out, pages, seen = [], 0, set()
        for i in range(len(edges) - 1):
            cursor = None
            while pages < config.SCAN_MAX_PAGES:
                params = {"status": "open", "limit": 1000,
                          "min_close_ts": edges[i], "max_close_ts": edges[i + 1],
                          "mve_filter": "exclude"}
                if cursor:
                    params["cursor"] = cursor
                data = self._get("/markets", params=params, timeout=60)
                if not data:
                    break
                pages += 1
                for m in data.get("markets", []) or []:
                    t = m.get("ticker", "")
                    if t.startswith("KXMVE") or t in seen:
                        continue
                    seen.add(t)
                    if not m.get("category"):
                        m["category"] = cats.get(t.split("-")[0], "")
                    out.append(m)
                cursor = data.get("cursor")
                if not cursor:
                    break
                time.sleep(0.3)
            if pages >= config.SCAN_MAX_PAGES:
                log("SCAN_MAX_PAGES reached; far-dated markets truncated", "WARN")
                break
        log(f"Fetched {len(out)} open markets via close-window feed across {pages} pages")
        if len(out) < 500:
            log(f"close-window feed returned only {len(out)} markets; falling back to events feed", "WARN")
            return self.get_all_open_markets_events()
        return out

    def get_all_open_markets_events(self) -> list:
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

    def get_closing_soon(self, min_hours: float = 2, max_hours: float = 72, max_pages: int = 30) -> list:
        """
        Open markets closing within a window, parsed. The events fetch above is
        capped at 50 pages and returns almost only long-dated markets (65,117 of
        65,284 closed in 10+ days), so the fast, liquid ones — daily crypto/index
        ladders, game-day markets, weather — never reached the scanner. Asking for
        a close-time window returns them. Combo (KXMVE) markets are skipped.
        """
        now = int(time.time())
        out, cursor = [], None
        for _ in range(max_pages):
            params = {"status": "open", "limit": 1000,
                      "min_close_ts": now + int(min_hours * 3600), "max_close_ts": now + int(max_hours * 3600)}
            if cursor:
                params["cursor"] = cursor
            data = self._get("/markets", params=params)
            if not data:
                break
            for raw in data.get("markets", []):
                if raw.get("ticker", "").startswith("KXMVE"):
                    continue
                m = parse_market(raw)
                if m:
                    out.append(m)
            cursor = data.get("cursor")
            if not cursor:
                break
            time.sleep(0.2)
        return out

    def get_settled_markets(self, limit: int = 200, pages: int = 1) -> list:
        """
        Fetch finalized markets via the /events endpoint (same source as the
        main scanner — Kalshi's /markets endpoint only returns parlay junk).
        Each market dict is flattened to carry `category` from its parent event
        and `result` ("yes"/"no") from the settlement payload.

        With pages>1, follows the cursor to pull multiple pages. Returns a flat
        list of market dicts across all finalized events.
        """
        out, cursor = [], None
        for _ in range(max(1, pages)):
            params = {"status": "settled", "limit": limit, "with_nested_markets": "true"}
            if cursor:
                params["cursor"] = cursor
            data = self._get("/events", params=params)
            if not data:
                # Try alternate status label — Kalshi has used both over time
                params["status"] = "finalized"
                data = self._get("/events", params=params)
            if not data:
                break
            events = data.get("events", []) or []
            for event in events:
                category = event.get("category", "")
                for m in event.get("markets", []) or []:
                    if not m.get("category"):
                        m["category"] = category
                    # Normalize settlement result to "yes" / "no" where present
                    r = (m.get("result") or m.get("settlement_value") or "").lower()
                    if r in ("yes", "no"):
                        m["result"] = r
                    out.append(m)
            cursor = data.get("cursor")
            if not cursor or not events:
                break
            time.sleep(0.2)
        return out

    # ── Portfolio (authenticated) ─────────────────────────────────────────────────

    def get_account_balance(self) -> Optional[float]:
        data = self._get("/portfolio/balance")
        return round(data.get("balance", 0) / 100, 2) if data else None

    def get_portfolio_positions(self) -> list:
        data = self._get("/portfolio/positions", params={"limit": 200})
        return (data or {}).get("market_positions", [])

    def get_market(self, ticker: str) -> Optional[dict]:
        """Fetch a single market's current state (prices, close_time, etc.)."""
        data = self._get(f"/markets/{ticker}")
        return (data or {}).get("market") or data

    def get_portfolio_total_value(self) -> Optional[float]:
        """
        Returns total account value: cash balance + open position market value.
        Position value is estimated at current YES/NO bid prices (conservative).
        Used for drawdown calculation — cash alone understates account health
        when bets are locked in open positions.
        """
        cash = self.get_account_balance()
        if cash is None:
            return None

        # Call the endpoint directly: get_portfolio_positions() turns a failed
        # call into [], which would silently value the open positions at $0.
        data = self._get("/portfolio/positions", params={"limit": 200})
        if data is None:
            return None
        positions = data.get("market_positions", [])
        if not positions:
            return cash

        pos_value = 0.0
        for pos in positions:
            ticker    = pos.get("ticker", "")
            count_raw = pos.get("position_fp") or pos.get("position") or 0
            count_fp  = float(count_raw)
            if not ticker or count_fp == 0:
                continue

            # Try market_exposure fields returned directly by positions endpoint
            for key in ("market_exposure_fp", "market_exposure"):
                raw = pos.get(key)
                if raw is not None:
                    val = float(raw)
                    # Kalshi may return cents (>10) or dollars (<= 1) — normalise
                    if abs(val) > 10:
                        val /= 100
                    pos_value += abs(val)
                    break
            else:
                # Fallback: fetch current market price for this ticker
                market = self.get_market(ticker)
                if not market:
                    continue
                if count_fp > 0:   # YES contracts — value at YES bid
                    bid = float(market.get("yes_bid_dollars") or
                                market.get("yes_bid", 0) or 0)
                    if bid > 1:
                        bid /= 100
                    pos_value += count_fp * bid
                else:              # NO contracts — value at NO bid = 1 - YES ask
                    ask = float(market.get("yes_ask_dollars") or
                                market.get("yes_ask", 0) or 0)
                    if ask > 1:
                        ask /= 100
                    pos_value += abs(count_fp) * max(0.0, 1.0 - ask)
                time.sleep(0.1)

        total = round(cash + pos_value, 2)
        log(f"Portfolio value: ${cash:.2f} cash + ${pos_value:.2f} positions = ${total:.2f}")
        return total

    def sell_position(self, ticker: str, side: str, count: int,
                      yes_price: int) -> dict:
        """Legacy signature: sell held `side`; yes_price is the YES-side price in cents."""
        px = yes_price if side.lower() == "yes" else 100 - yes_price
        return self.place_order_v2(ticker, "sell", side, count, px)


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

        last_price = 0
        try:
            if raw.get("last_price_dollars") not in (None, ""):
                last_price = int(round(float(raw["last_price_dollars"]) * 100))
            elif raw.get("last_price") not in (None, ""):
                last_price = int(round(float(raw["last_price"])))
        except Exception:
            last_price = 0
        segs = ticker.split("-")
        event = raw.get("event_ticker") or "-".join(segs[:2])

        return {
            "series":          segs[0],
            "event":           event,
            "last_price":      last_price,
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
