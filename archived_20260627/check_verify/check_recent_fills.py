#!/usr/bin/env python3
"""Check recent fills on main wallet"""
import sys
sys.path.insert(0, r'D:\dev\trading')

from hyperliquid.info import Info

BASE_URL = "https://api.hyperliquid-testnet.xyz"
info = Info(base_url=BASE_URL)

MAIN_WALLET = '0x97c465489243175580fcDe624c2ef640c1897a00'

print("=" * 60)
print("RECENT FILLS ON MAIN WALLET")
print("=" * 60)

fills = info.user_fills(MAIN_WALLET)
print(f"\nTotal fills: {len(fills)}")
print()

# Show last 10 fills
for fill in fills[-10:]:
    coin = fill.get('coin')
    dir = fill.get('dir')
    sz = fill.get('sz')
    px = fill.get('px')
    oid = fill.get('oid')
    print(f"{coin:4} {dir:12} {sz:8} @ ${px:8} (OID: {oid})")
