#!/usr/bin/env python3
"""Check all positions on trading wallet"""
import os
import sys

sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

from hyperliquid.info import Info

BASE_URL = "https://api.hyperliquid-testnet.xyz"
info = Info(base_url=BASE_URL)

TRADING_WALLET = '0x89823A4f85cc8ef3A5574E8a56741A7b4562f288'

print("=" * 60)
print("POSITIONS ON TRADING WALLET")
print("=" * 60)

state = info.user_state(TRADING_WALLET)
positions = state.get('assetPositions', [])

print(f"Wallet: {TRADING_WALLET}")
print(f"Open positions: {len(positions)}\n")

for pos in positions:
    p = pos.get('position', {})
    coin = p.get('coin', 'Unknown')
    size = float(p.get('szi', 0))
    entry = float(p.get('entryPx', 0))
    leverage = float(p.get('leverage', {}).get('value', 0))
    unrealized = float(p.get('unrealizedPnl', 0))
    side = 'LONG' if size > 0 else 'SHORT'
    print(f"{coin}: {side} {abs(size)} @ ${entry} (lev: {leverage}x, PnL: ${unrealized:.2f})")
