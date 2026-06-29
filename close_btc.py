#!/usr/bin/env python3
"""Close BTC position using Hyperliquid SDK"""

from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from eth_account import Account
from dotenv import load_dotenv
import os

load_dotenv(r'C:\Users\mrztms\.openclaw\.env')

wallet_address = os.getenv('HYPERLIQUID_WALLET')
private_key = os.getenv('HYPERLIQUID_PRIVATE_KEY')
base_url = os.getenv('HYPERLIQUID_BASE_URL', 'https://api.hyperliquid-testnet.xyz')

print(f'Wallet: {wallet_address}')

# Create LocalAccount from private key
account = Account.from_key(private_key)
print(f'Account address: {account.address}')

# Initialize
print('\nConnecting to Hyperliquid...')
info = Info(base_url, skip_ws=True)

print('Creating exchange client...')
exchange = Exchange(account, base_url=base_url)

# Check position
print('\nChecking positions...')
positions = info.user_state(wallet_address)

found = False
for asset_pos in positions.get('assetPositions', []):
    pos = asset_pos['position']
    coin = pos['coin']
    size = float(pos['szi'])
    entry = pos.get('entryPx', 'N/A')
    print(f'  {coin}: {size} @ {entry}')
    
    if coin == 'BTC' and abs(size) > 0:
        found = True
        print(f'\nClosing {size} BTC...')
        result = exchange.market_close(coin)
        print(f'Result: {result}')

if not found:
    print('\nNo BTC position found to close.')

print('\nDone.')
