#!/usr/bin/env python3
"""Fix ETH orders - cancel existing and place both SL+TP"""
import sys
sys.path.insert(0, r'D:\dev\trading')

from trade_executor import HyperliquidClient
import json

client = HyperliquidClient()

# ETH position details
symbol = 'ETH'
sz = 0.0337
entry_price = 1569.1
sl_price = entry_price * 0.985  # 1.5% below entry
tp_price = entry_price * 1.03   # 3% above entry

print(f"ETH Position: LONG {sz} @ ${entry_price}")
print(f"SL: ${sl_price:.2f}")
print(f"TP: ${tp_price:.2f}")

# Round to tick size
tick = 0.05
multiplier = 100

def round_to_tick(price):
    price_int = int(round(price * multiplier))
    tick_int = int(round(tick * multiplier))
    ticks = price_int // tick_int
    result = ticks * tick
    # Format to avoid floating point display issues
    return round(result, 2)

rounded_sl = round_to_tick(sl_price)
rounded_tp = round_to_tick(tp_price)

print(f"Rounded SL: ${rounded_sl}")
print(f"Rounded TP: ${rounded_tp}")

# Get current orders
orders = client._exchange.info.open_orders(client.MAIN_WALLET)
eth_orders = [o for o in orders if o.get('coin') == 'ETH']

print(f"\nExisting ETH orders: {len(eth_orders)}")
for o in eth_orders:
    print(f"  OID {o.get('oid')}: {o.get('side')} @ ${o.get('limitPx')}")

# Cancel existing ETH orders
if eth_orders:
    print(f"\nCancelling {len(eth_orders)} ETH order(s)...")
    for o in eth_orders:
        oid = o.get('oid')
        try:
            result = client._exchange.cancel_order(symbol, oid)
            print(f"  Cancel OID {oid}: {result}")
        except Exception as e:
            print(f"  Cancel OID {oid} failed: {e}")

# Now place both SL and TP
print("\nPlacing SL trigger order...")
try:
    result = client.place_trigger_order(
        coin=symbol,
        is_buy=False,
        sz=sz,
        trigger_px=rounded_sl,
        limit_px=rounded_sl,  # Market execution on trigger
        tpsl='sl',
        is_market=False,
        reduce_only=True
    )
    print(f"SL Response: {json.dumps(result, indent=2)}")
except Exception as e:
    print(f"SL Error: {e}")

print("\nPlacing TP trigger order...")
try:
    result = client.place_trigger_order(
        coin=symbol,
        is_buy=False,
        sz=sz,
        trigger_px=rounded_tp,
        limit_px=rounded_tp,  # Market execution on trigger
        tpsl='tp',
        is_market=False,
        reduce_only=True
    )
    print(f"TP Response: {json.dumps(result, indent=2)}")
except Exception as e:
    print(f"TP Error: {e}")

# Verify
print("\n=== Final ETH Orders ===")
orders = client._exchange.info.open_orders(client.MAIN_WALLET)
eth_orders = [o for o in orders if o.get('coin') == 'ETH']
for o in eth_orders:
    print(f"  OID {o.get('oid')}: {o.get('side')} @ ${o.get('limitPx')} (reduceOnly={o.get('reduceOnly')})")
