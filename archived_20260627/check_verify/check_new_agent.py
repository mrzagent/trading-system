#!/usr/bin/env python3
"""Check new authorized agent wallet"""
import os
import sys

# New agent wallet
os.environ['HYPERLIQUID_WALLET'] = '0x4B9e7D98c7acea1DeD7A426eeE7E012A195Fd9af'
os.environ['HYPERLIQUID_PRIVATE_KEY'] = '0x33008c2119faeafb7b9c9261ef31c8829d5c3fdf60253f1123012d24cf51359d'

sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

from eth_account import Account
from hyperliquid.info import Info

account = Account.from_key(os.environ['HYPERLIQUID_PRIVATE_KEY'])
wallet = account.address

print("=" * 60)
print("NEW AUTHORIZED AGENT WALLET CHECK")
print("=" * 60)
print(f"Wallet Address: {wallet}")
print()

BASE_URL = "https://api.hyperliquid-testnet.xyz"
info = Info(base_url=BASE_URL)

# Check balance
state = info.user_state(wallet)
account_value = float(state.get('marginSummary', {}).get('accountValue', 0))
withdrawable = float(state.get('withdrawable', 0))
positions = state.get('assetPositions', [])

print(f"Account Value: ${account_value:.2f}")
print(f"Withdrawable: ${withdrawable:.2f}")
print(f"Positions: {len(positions)}")

if positions:
    for pos in positions:
        p = pos.get('position', {})
        coin = p.get('coin', '')
        size = p.get('szi', 0)
        entry = p.get('entryPx', 0)
        print(f"  {coin}: {size} @ ${entry}")
else:
    print("  (No positions)")

# Check fills
fills = info.user_fills(wallet)
print(f"\nTotal Fills: {len(fills)}")
if fills:
    for fill in fills[-3:]:
        print(f"  {fill.get('coin')} {fill.get('dir')} {fill.get('sz')} @ ${fill.get('px')}")

print("\n" + "=" * 60)
if account_value > 0:
    print("[OK] Wallet has USDC and is ready for trading!")
else:
    print("[NOTE] Wallet shows $0 balance - may need more time to settle")
