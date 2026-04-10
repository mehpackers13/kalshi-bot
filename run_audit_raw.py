import os, sys, json, datetime
sys.path.insert(0, '.')
from kalshi_api import KalshiAPI

api = KalshiAPI()
if not api.login():
    print("AUTH FAILED"); sys.exit(1)

bal = api.get_account_balance()
print(f"\nLIVE BALANCE: ${bal:.2f}\n")

# ── Raw positions dump ──────────────────────────────────────
print("=== RAW POSITIONS (first 2) ===")
pos_resp = api._get("/portfolio/positions", params={"limit": 100})
positions = (pos_resp or {}).get("market_positions", [])
if positions:
    for p in positions[:2]:
        print(json.dumps(p, indent=2))
else:
    print("(empty) full response:", json.dumps(pos_resp, indent=2)[:500])

# ── Raw orders dump ─────────────────────────────────────────
print("\n=== RAW ORDERS (first 2) ===")
ord_resp = api._get("/portfolio/orders", params={"limit": 50})
orders = (ord_resp or {}).get("orders", [])
if orders:
    for o in orders[:2]:
        print(json.dumps(o, indent=2))
else:
    print("(empty) keys in response:", list((ord_resp or {}).keys()))

# ── Raw fills dump ──────────────────────────────────────────
print("\n=== RAW FILLS (first 2) ===")
fills_resp = api._get("/portfolio/fills", params={"limit": 20})
fills = (fills_resp or {}).get("fills", [])
if fills:
    for f in fills[:2]:
        print(json.dumps(f, indent=2))
else:
    print("(empty) keys:", list((fills_resp or {}).keys()))

# ── Try trades endpoint ─────────────────────────────────────
print("\n=== TRADES ===")
trades_resp = api._get("/portfolio/trades", params={"limit": 20})
print("keys:", list((trades_resp or {}).keys()))
trades = list((trades_resp or {}).values())[0] if trades_resp else []
if isinstance(trades, list) and trades:
    print(json.dumps(trades[0], indent=2))

print("\n=== DONE ===")
