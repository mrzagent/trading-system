#!/usr/bin/env python3
import os
import sys
sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

from dotenv import load_dotenv
load_dotenv(r'C:\Users\mrztms\.openclaw\.env')

from hyperliquid.info import Info

BASE_URL = 'https://api.hyperliquid-testnet.xyz'
TRADING_WALLET = '0x89823a4f85cc8ef3a5574e8a56741a7b4562f288'

info = Info(base_url=BASE_URL)
user_state = info.user_state(TRADING_WALLET)

account_value = float(user_state.get('marginSummary', {}).get('accountValue', 0))
withdrawable = float(user_state.get('withdrawable', 0))
positions = user_state.get('assetPositions', [])

print(f'Trading Wallet: {TRADING_WALLET}')
print(f'Account Value: ${account_value:.2f}')
print(f'Withdrawable: ${withdrawable:.2f}')
print(f'Positions: {len(positions)}')
for pos in positions:
    p = pos.get('position', {})
    coin = p.get('coin', 'Unknown')
    size = p.get('szi', 0)
    entry = p.get('entryPx', 0)
    print(f'  - {coin}: {size} @ ${entry}')
