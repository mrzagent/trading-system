#!/usr/bin/env python3
"""Check both mainnet and testnet for MAIN wallet"""
import sys
sys.path.insert(0, r'D:\dev\trading')

from hyperliquid.info import Info

main_wallet = '0x97c465489243175580fcDe624c2ef640c1897a00'

print('=== MAINNET (Main Wallet) ===')
try:
    info_main = Info(base_url='https://api.hyperliquid.xyz')
    state = info_main.user_state(main_wallet)
    balance = float(state.get('marginSummary', {}).get('accountValue', 0))
    print(f'Main wallet: ${balance:.2f}')
except Exception as e:
    print(f'Error: {e}')

print()
print('=== TESTNET (Main Wallet) ===')
try:
    info_test = Info(base_url='https://api.hyperliquid-testnet.xyz')
    state = info_test.user_state(main_wallet)
    balance = float(state.get('marginSummary', {}).get('accountValue', 0))
    print(f'Main wallet: ${balance:.2f}')
except Exception as e:
    print(f'Error: {e}')
