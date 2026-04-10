import os, sys, json
sys.path.insert(0, '.')
from kalshi_api import KalshiAPI

api = KalshiAPI()
if not api.login():
    print("AUTH FAILED"); sys.exit(1)

bal = api.get_account_balance()
print(f"\n{'='*60}")
print(f"LIVE BALANCE: ${bal:.2f}")
print(f"{'='*60}\n")

# ── All positions ────────────────────────────────────────────
print("=== OPEN POSITIONS ===")
pos_resp = api._get("/portfolio/positions", params={"limit": 100})
positions = (pos_resp or {}).get("market_positions", [])
total_exposure = 0
for p in positions:
    ticker   = p.get("ticker", "?")
    pos_fp   = float(p.get("position_fp", 0))
    exposure = float(p.get("market_exposure_dollars", 0))
    traded   = float(p.get("total_traded_dollars", 0))
    pnl      = float(p.get("realized_pnl_dollars", 0))
    fees     = float(p.get("fees_paid_dollars", 0))
    side     = "NO" if pos_fp < 0 else ("YES" if pos_fp > 0 else "SETTLED")
    qty      = abs(pos_fp)
    total_exposure += exposure
    print(f"  {ticker}")
    print(f"    side={side}  qty={qty:.0f}ct  cost=${traded:.2f}  fees=${fees:.2f}  exposure=${exposure:.2f}  realized_pnl=${pnl:.2f}")

print(f"\nTotal open positions: {len(positions)}")
print(f"Total $ at risk: ${total_exposure:.2f}\n")

# ── All orders ───────────────────────────────────────────────
print("=== ALL ORDERS ===")
ord_resp = api._get("/portfolio/orders", params={"limit": 50})
orders = (ord_resp or {}).get("orders", [])
total_cost = 0
for o in sorted(orders, key=lambda x: x.get("created_time","")):
    created  = o.get("created_time", "?")[:19]
    ticker   = o.get("ticker", "?")
    side     = o.get("side", "?").upper()
    qty      = float(o.get("fill_count_fp", 0))
    yes_px   = float(o.get("yes_price_dollars", 0))
    no_px    = float(o.get("no_price_dollars", 0))
    taker_cost = float(o.get("taker_fill_cost_dollars", 0))
    maker_cost = float(o.get("maker_fill_cost_dollars", 0))
    taker_fee  = float(o.get("taker_fees_dollars", 0))
    status   = o.get("status", "?")
    oid      = o.get("order_id", "?")[:8]
    price    = yes_px if side=="YES" else no_px
    cost     = taker_cost + maker_cost
    total_cost += cost
    print(f"  [{created}] {ticker}")
    print(f"    BUY {side} {qty:.0f}ct @ ${price:.2f}/ct  filled_cost=${cost:.2f}  fees=${taker_fee:.2f}  status={status}  id={oid}")

print(f"\nTotal orders: {len(orders)}")
print(f"Total spent on orders: ${total_cost:.2f}\n")

# ── All fills ────────────────────────────────────────────────
print("=== ALL FILLS ===")
fills_resp = api._get("/portfolio/fills", params={"limit": 50})
fills = (fills_resp or {}).get("fills", [])
for f in sorted(fills, key=lambda x: x.get("created_time","")):
    created = f.get("created_time","?")[:19]
    ticker  = f.get("ticker","?")
    side    = f.get("side","?").upper()
    qty     = float(f.get("count_fp",0))
    yes_px  = float(f.get("yes_price_dollars",0))
    no_px   = float(f.get("no_price_dollars",0))
    fee     = float(f.get("fee_cost",0))
    price   = yes_px if side=="YES" else no_px
    cost    = qty * price
    print(f"  [{created}] {ticker}  BUY {side} {qty:.0f}ct @ ${price:.2f}  cost=${cost:.2f}  fee=${fee:.2f}")

print(f"\nTotal fills: {len(fills)}")
print("\n=== AUDIT COMPLETE ===")
