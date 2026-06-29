#!/usr/bin/env python3
"""Check ETH market config"""
import sys
sys.path.insert(0, r'D:\dev\trading')
from hyperliquid.info import Info

info = Info(base_url='https://api.hyperliquid-testnet.xyz')
meta = info.meta()

for asset in meta.get('universe', []):
    if asset.get('name') == 'ETH':
        print('ETH Config:')
        print(f"  szDecimals: {asset.get('szDecimals')}")
        print(f"  minSz: {asset.get('minSz')}")
        print(f"  maxLeverage: {asset.get('maxLeverage')}")
        print()

# Get current price
mids = info.all_mids()
eth_price = float(mids.get('ETH', 0))
print(f'Current ETH price: ${eth_price:,.2f}')
print(f'$50 = {50/eth_price:.6f} ETH')
print(f'$100 = {100/eth_price:.6f} ETH')

# Calculate proper size with correct decimals
min_sz = 0.001  # Assuming minSz from config
sz_decimals = 3
sz_50 = round(50 / eth_price, sz_decimals)
sz_100 = round(100 / eth_price, sz_decimals)
print(f'\nProper size for $50: {sz_50} ETH')
print(f'Proper size for $100: {sz_100} ETH')
