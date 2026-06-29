#!/usr/bin/env python3
"""Check ALL fills on trading wallet"""
import os
import sys

sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

from hyperliquid.info import Info

BASE_URL = "https://api.hyperliquid-testnet.xyz"
info = Info(base_url=BASE_URL)

TRADING_WALLET = '0x89823A4f85cc8ef3A5574E8a56741A7b4562f288'

print("=" * 60)
print("ALL FILLS ON TRADING WALLET")
print("=" * 60)

fills = info.user_fills(TRADING_WALLET)

if not fills:
    print("No fills found")
else:
    print(f"Total fills: {len(fills)}\n")
    for fill in fills[-20:]:  # Last 20 fills
        coin = fill.get('coin', 'Unknown')
        side = 'BUY' if fill.get('side') == 'B' else 'SELL'
        size = fill.get('sz', 0)
        price = fill.get('px', 0)
        time = fill.get('time', 0)
        print(f"{coin} {side} {size} @ ${price} (time: {time})")
