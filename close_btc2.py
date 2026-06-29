#!/usr/bin/env python3
"""Close BTC position using Hyperliquid SDK - Method 2"""

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
exchange = Exchange(account, base_url=base_url)

# Check position
print('\nChecking positions...')
positions = info.user_state(wallet_address)

for asset_pos in positions.get('assetPositions', []):
    pos = asset_pos['position']
    coin = pos['coin']
    size = float(pos['szi'])
    entry = pos.get('entryPx', 'N/A')
    print(f'  {coin}: {size} @ {entry}')
    
    if coin == 'BTC' and abs(size) > 0:
        # Get current price
        mids = info.all_mids()
        current_px = float(mids.get(coin, 0))
        print(f'\nCurrent {coin} price: ${current_px:,.2f}')
        
        # Determine direction - we need to sell to close long position
        is_buy = size < 0  # False for long (sell to close)
        
        print(f'\nPlacing market order to close {abs(size)} {coin}...')
        print(f'  Side: {"BUY" if is_buy else "SELL"}')
        print(f'  Size: {abs(size)}')
        
        # Use market order - "Ioc" means Immediate or Cancel (fills immediately at best price)
        # Round price to whole number for BTC (tick size is $1)
        limit_px = int(current_px * 0.95 if not is_buy else current_px * 1.05)  # Slippage buffer
        print(f'  Limit price: ${limit_px}')
        
        result = exchange.order(
            name=coin,
            is_buy=is_buy,
            sz=abs(size),
            limit_px=limit_px,
            order_type={"limit": {"tif": "Ioc"}},
            reduce_only=True
        )
        print(f'\nOrder result: {result}')

print('\nDone.')
