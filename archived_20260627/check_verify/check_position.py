#!/usr/bin/env python3
import os
import sys
sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

# FORCE CORRECT KEY
os.environ['HYPERLIQUID_PRIVATE_KEY'] = '0x5dc4eea052a2eac43ce453bbb116ae6c9f8a87daf3ccb455064cb9d0dbe62906'

from eth_account import Account
from hyperliquid.info import Info

account = Account.from_key(os.environ['HYPERLIQUID_PRIVATE_KEY'])
info = Info(base_url='https://api.hyperliquid-testnet.xyz')
state = info.user_state(account.address)

print("=" * 60)
print("AGENT WALLET POSITION CHECK")
print("=" * 60)
print(f"Wallet: {account.address}")
av = float(state.get('marginSummary', {}).get('accountValue', 0))
print(f"Account Value: ${av:.2f}")

positions = state.get('assetPositions', [])
print(f"\nOpen Positions: {len(positions)}")
for pos in positions:
    p = pos.get('position', {})
    coin = p.get('coin', 'Unknown')
    size = p.get('szi', 0)
    entry = p.get('entryPx', 0)
    pnl = p.get('unrealizedPnl', 0)
    print(f"  {coin}: {size} @ ${entry} (PnL: ${pnl})")
