#!/usr/bin/env python3
"""Check MAIN wallet for ETH fills"""
import sys
sys.path.insert(0, r'D:\dev\trading')

from hyperliquid.info import Info

MAIN_WALLET = '0x97c465489243175580fcDe624c2ef640c1897a00'

info = Info(base_url='https://api.hyperliquid-testnet.xyz')

print("=" * 60)
print("ALL FILLS ON MAIN WALLET")
print("=" * 60)

fills = info.user_fills(MAIN_WALLET)
print(f"\nTotal fills: {len(fills)}")
print()

# Show all fills
for fill in fills:
    oid = fill.get('oid')
    coin = fill.get('coin')
    dir = fill.get('dir')
    sz = fill.get('sz')
    px = fill.get('px')
    print(f"OID {oid}: {coin} {dir} {sz} @ ${px}")

print("\n" + "=" * 60)
print("Looking for ETH fills...")
eth_fills = [f for f in fills if f.get('coin') == 'ETH']
print(f"ETH fills: {len(eth_fills)}")
for fill in eth_fills:
    print(f"  {fill}")

print("\nLooking for OIDs 55433722333 or 55435536626...")
target_oids = [55433722333, 55435536626]
for oid in target_oids:
    found = [f for f in fills if f.get('oid') == oid]
    print(f"OID {oid}: {'FOUND' if found else 'NOT FOUND'}")
