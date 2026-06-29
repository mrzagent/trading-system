#!/usr/bin/env python3
"""Check order status by OID"""
import sys
sys.path.insert(0, r'D:\dev\trading')

from hyperliquid.info import Info

info = Info(base_url='https://api.hyperliquid-testnet.xyz')

oid = 55433722333  # ETH order OID

print(f"Checking order status for OID: {oid}")
print()

# Unfortunately the SDK doesn't have a direct order status query
# Let's check recent fills again with full details
wallet = '0x89823A4f85cc8ef3A5574E8a56741A7b4562f288'

print(f"Wallet: {wallet}")
print()

# Get all fills
fills = info.user_fills(wallet)
print(f"All fills ({len(fills)} total):")
for fill in fills:
    print(f"  OID {fill.get('oid')}: {fill.get('coin')} {fill.get('side')} {fill.get('sz')} @ ${fill.get('px')} - {fill.get('dir')}")
