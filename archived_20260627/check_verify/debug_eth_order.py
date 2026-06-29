#!/usr/bin/env python3
"""Debug order status after ETH trade attempt"""
import sys
sys.path.insert(0, r'D:\dev\trading')

from hyperliquid.info import Info

wallet = '0x89823A4f85cc8ef3A5574E8a56741A7b4562f288'
oid = 55435536626  # ETH order from last attempt

info = Info(base_url='https://api.hyperliquid-testnet.xyz')

print(f"Debugging order {oid}")
print(f"Wallet: {wallet}")
print()

# Check user state
state = info.user_state(wallet)
print(f"Account Value: ${float(state.get('marginSummary', {}).get('accountValue', 0)):.2f}")
print(f"Positions: {len(state.get('assetPositions', []))}")
print()

# Check all fills
fills = info.user_fills(wallet)
print(f"All fills ({len(fills)} total):")
for fill in fills:
    print(f"  OID {fill.get('oid')}: {fill.get('coin')} {fill.get('dir')} {fill.get('sz')} @ ${fill.get('px')}")

# Check if our OID is in the fills
fill_oids = [f.get('oid') for f in fills]
print(f"\nOID {oid} in fills: {oid in fill_oids}")

# Try to get order status via different method
print("\n" + "=" * 60)
print("Checking all open orders:")
open_orders = info.open_orders(wallet)
print(f"Open orders: {len(open_orders)}")
for order in open_orders:
    print(f"  {order}")
