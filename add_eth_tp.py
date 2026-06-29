#!/usr/bin/env python3
"""Add TP order to existing ETH long position"""
import sys
sys.path.insert(0, r'D:\dev\trading')

from trade_executor import HyperliquidClient
import json

client = HyperliquidClient()

# ETH position details
symbol = 'ETH'
side = 'long'  # Current position is long
sz = 0.0337
entry_price = 1569.1

# Calculate TP price (3% above entry for long)
tp_pct = 0.03  # 3%
tp_price = entry_price * (1 + tp_pct)
print(f"ETH Position: LONG {sz} @ ${entry_price}")
print(f"TP Price: ${tp_price:.2f} ({tp_pct*100:.1f}% above entry)")

# Get current price for limit_px
current_price = client.get_mid_price('ETH')
print(f"Current ETH price: ${current_price}")

# Round to tick size using integer math
tick_sizes = {'BTC': 1, 'ETH': 0.05, 'SOL': 0.01}
tick = tick_sizes.get('ETH', 0.01)
multiplier = 100 if tick < 1 else 1

# Round TP price to tick size
tp_price_int = int(round(tp_price * multiplier))
tick_int = int(round(tick * multiplier))
tp_ticks = tp_price_int // tick_int
rounded_tp = tp_ticks * tick
print(f"Rounded TP: ${rounded_tp}")

# Round current price for limit_px - use FLOOR to ensure it's below TP
current_price_int = int(round(current_price * multiplier))
current_ticks = current_price_int // tick_int
rounded_limit = current_ticks * tick
# Ensure limit_px is slightly below current to guarantee execution
rounded_limit = min(rounded_limit, rounded_tp - tick)
print(f"Rounded limit_px: ${rounded_limit}")

# For long position, TP is a sell order (is_buy=False)
is_buy = False

print(f"\nPlacing TP trigger order:")
print(f"  Coin: {symbol}")
print(f"  Side: {'BUY' if is_buy else 'SELL'}")
print(f"  Size: {sz}")
print(f"  Trigger: ${rounded_tp}")
print(f"  Limit: ${rounded_limit}")

try:
    result = client.place_trigger_order(
        coin=symbol,
        is_buy=is_buy,
        sz=sz,
        trigger_px=rounded_tp,
        limit_px=rounded_limit,
        tpsl='tp',
        is_market=True,
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
    import traceback
    traceback.print_exc()
