#!/usr/bin/env python3
"""Verify testnet connection and wallet balance"""
import os
import sys
sys.path.insert(0, r'D:\dev\trading')

# Force testnet
os.environ['HYPERLIQUID_WALLET'] = '0x89823A4f85cc8ef3A5574E8a56741A7b4562f288'
os.environ['HYPERLIQUID_PRIVATE_KEY'] = '0x5dc4eea052a2eac43ce453bbb116ae6c9f8a87daf3ccb455064cb9d0dbe62906'

from hyperliquid.info import Info
from eth_account import Account

account = Account.from_key(os.environ['HYPERLIQUID_PRIVATE_KEY'])
wallet = account.address

print(f'Wallet being queried: {wallet}')
print(f'Expected: 0x89823A4f85cc8ef3A5574E8a56741A7b4562f288')
print(f'Match: {wallet.lower() == "0x89823a4f85cc8ef3a5574e8a56741a7b4562f288"}')
print()

info = Info(base_url='https://api.hyperliquid-testnet.xyz')
print('API: https://api.hyperliquid-testnet.xyz (TESTNET)')
print()

state = info.user_state(wallet)
print(f'Raw state response:')
print(f'  marginSummary: {state.get("marginSummary", {})}')
print(f'  assetPositions: {len(state.get("assetPositions", []))} positions')

balance = float(state.get('marginSummary', {}).get('accountValue', 0))
print(f'\nParsed Account Value: ${balance:.2f}')
