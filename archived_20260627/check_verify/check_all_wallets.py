#!/usr/bin/env python3
"""Check trading wallet balance"""
import os
import sys

sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

from hyperliquid.info import Info

BASE_URL = "https://api.hyperliquid-testnet.xyz"
info = Info(base_url=BASE_URL)

TRADING_WALLET = '0x89823A4f85cc8ef3A5574E8a56741A7b4562f288'

print("=" * 60)
print("TRADING WALLET")
print("=" * 60)

state = info.user_state(TRADING_WALLET)
balance = float(state.get('marginSummary', {}).get('accountValue', 0))
positions = len(state.get('assetPositions', []))

print(f"Wallet: {TRADING_WALLET}")
print(f"Balance: ${balance:.2f}")
print(f"Positions: {positions}")
