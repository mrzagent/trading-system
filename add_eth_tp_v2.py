#!/usr/bin/env python3
"""Add TP order to existing ETH long position - try different approach"""
import sys
sys.path.insert(0, r'D:\dev\trading')

from trade_executor import HyperliquidClient
import json

client = HyperliquidClient()

# ETH position details
symbol = 'ETH'
side = 'long'
sz = 0.0337
entry_price = 1569.1

# Calculate TP price (3% above entry)
tp_price = entry_price * 1.03
print(f"ETH Position: LONG {sz} @ ${entry_price}")
print(f"TP Target: ${tp_price:.2f}")

# Round to tick size
tick = 0.05
multiplier = 100
tp_int = int(round(tp_price * multiplier))
tick_int = int(round(tick * multiplier))
tp_ticks = tp_int // tick_int
rounded_tp = tp_ticks * tick

print(f"Rounded TP: ${rounded_tp}")

# For the limit price, use a price that guarantees execution
# Use the TP price itself as limit (market order on trigger)
limit_px = rounded_tp

print(f"\nPlacing TP trigger order:")
print(f"  trigger_px: ${rounded_tp}")
print(f"  limit_px: ${limit_px}")

try:
    # Try with is_market=False and explicit limit price
    result = client.place_trigger_order(
        coin=symbol,
        is_buy=False,  # Sell for TP on long
        sz=sz,
        trigger_px=rounded_tp,
        limit_px=limit_px,  # Same as trigger for market execution
        tpsl='tp',
        is_market=False,  # Try with limit order
        reduce_only=True
    )
    print(f"\nResponse: {json.dumps(result, indent=2)}")
    
    if result.get('status') == 'ok':
        statuses = result.get('response', {}).get('data', {}).get('statuses', [])
        if statuses:
            if 'error' in statuses[0]:
                print(f"Error: {statuses[0]['error']}")
            elif 'resting' in statuses[0]:
                oid = statuses[0]['resting']['oid']
                print(f"Success! TP Order ID: {oid}")
            else:
                print(f"Status: {statuses[0]}")
except Exception as e:
    print(f"Exception: {e}")
