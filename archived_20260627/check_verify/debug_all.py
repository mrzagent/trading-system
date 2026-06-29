#!/usr/bin/env python3
"""Debug all wallet balances on testnet"""
import sys
sys.path.insert(0, r'D:\dev\trading')

from hyperliquid.info import Info

wallets = {
    'Agent': '0x89823A4f85cc8ef3A5574E8a56741A7b4562f288',
    'Main': '0x97c465489243175580fcDe624c2ef640c1897a00'
}

info = Info(base_url='https://api.hyperliquid-testnet.xyz')

print('=== TESTNET BALANCES ===')
print()

for name, wallet in wallets.items():
    state = info.user_state(wallet)
    balance = float(state.get('marginSummary', {}).get('accountValue', 0))
    raw_usd = float(state.get('marginSummary', {}).get('totalRawUsd', 0))
    print(f'{name} Wallet ({wallet}):')
    print(f'  accountValue: ${balance:.2f}')
    print(f'  totalRawUsd: ${raw_usd:.2f}')
    print()
