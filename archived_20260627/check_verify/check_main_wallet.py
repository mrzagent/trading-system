#!/usr/bin/env python3
import os
import sys
sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

from hyperliquid.info import Info

info = Info(base_url='https://api.hyperliquid-testnet.xyz')

# Main wallet
wallet = "0x97c465489243175580fcDe624c2ef640c1897a00"
state = info.user_state(wallet)

print("=" * 60)
print("MAIN WALLET POSITIONS")
print("=" * 60)
print(f"Wallet: {wallet}")
print(f"Account Value: ${float(state.get('marginSummary', {}).get('accountValue', 0)):.2f}")

positions = state.get('assetPositions', [])
print(f"\nPositions: {len(positions)}")
for pos in positions:
    p = pos.get('position', {})
    coin = p.get('coin', 'Unknown')
    size = p.get('szi', 0)
    entry = p.get('entryPx', 0)
    pnl = p.get('unrealizedPnl', 0)
    margin = p.get('marginUsed', 0)
    print(f"\n  {coin}:")
    print(f"    Size: {size}")
    print(f"    Entry: ${entry}")
    print(f"    PnL: {pnl}")
    print(f"    Margin Used: {margin}")
