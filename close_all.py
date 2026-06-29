#!/usr/bin/env python3
"""Close all open positions on HyperLiquid using market orders"""

from trade_executor import HyperliquidClient
import time

client = HyperliquidClient()

# Get positions
positions = client.get_positions()
print(f"Found {len(positions)} position(s) on HyperLiquid:")
for pos in positions:
    print(f"  {pos['coin']}: size={pos['size']}, value=${pos['position_value']:.2f}")

# Close each position by placing opposite market order
for pos in positions:
    coin = pos['coin']
    size = abs(float(pos['size']))
    current_size = float(pos['size'])
    
    if size == 0:
        continue
    
    # Determine direction to close
    if current_size > 0:
        # Long position - sell to close
        is_buy = False
        print(f"\nClosing {coin} LONG: selling {size}")
    else:
        # Short position - buy to close
        is_buy = True
        print(f"\nClosing {coin} SHORT: buying {size}")
    
    # Get current price and add slippage for market-like execution
    mid_price = client.get_mid_price(coin)
    tick_sizes = {'BTC': 1, 'ETH': 0.05, 'SOL': 0.01}
    tick = tick_sizes.get(coin, 0.01)
    
    # For market order effect, use price slightly worse than mid
    if is_buy:
        # Buying - use higher price
        limit_px = round(round((mid_price * 1.005) / tick) * tick, 8)
    else:
        # Selling - use lower price  
        limit_px = round(round((mid_price * 0.995) / tick) * tick, 8)
    
    print(f"  Mid price: ${mid_price}, Order price: ${limit_px}")
    
    # Place IOC order to close
    result = client.place_order(coin, is_buy, size, limit_px, order_type='Ioc', reduce_only=True)
    print(f"  Result: {result}")
    
    time.sleep(0.5)

# Verify closure
print("\nVerifying...")
positions = client.get_positions()
print(f"Remaining positions: {len(positions)}")
for pos in positions:
    print(f"  {pos['coin']}: size={pos['size']}")

if not positions:
    print("\n✅ All positions closed successfully")
else:
    print("\n⚠️ Some positions remain")
