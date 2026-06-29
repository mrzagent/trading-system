#!/usr/bin/env python3
"""Check both mainnet and testnet for trading wallet"""
import os
import sys

sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

from hyperliquid.info import Info

TRADING_WALLET = '0x89823a4f85cc8ef3a5574e8a56741a7b4562f288'

print("=" * 60)
print("TRADING WALLET - BOTH NETWORKS")
print("=" * 60)

# Check mainnet
print("\n--- MAINNET ---")
info_main = Info(base_url="https://api.hyperliquid.xyz")
try:
    state = info_main.user_state(TRADING_WALLET)
    balance = float(state.get('marginSummary', {}).get('accountValue', 0))
    print(f'Balance: ${balance:.2f}')
except Exception as e:
    print(f'Error: {e}')

# Check testnet
print("\n--- TESTNET ---")
info_test = Info(base_url="https://api.hyperliquid-testnet.xyz")
try:
    state = info_test.user_state(TRADING_WALLET)
    balance = float(state.get('marginSummary', {}).get('accountValue', 0))
    print(f'Balance: ${balance:.2f}')
except Exception as e:
    print(f'Error: {e}')
