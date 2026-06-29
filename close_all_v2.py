#!/usr/bin/env python3
"""Close all positions using market_open with opposite side"""
import os
import sys

os.environ['HYPERLIQUID_WALLET'] = '0x89823A4f85cc8ef3A5574E8a56741A7b4562f288'
os.environ['HYPERLIQUID_PRIVATE_KEY'] = '0x5dc4eea052a2eac43ce453bbb116ae6c9f8a87daf3ccb455064cb9d0dbe62906'

sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

from eth_account import Account
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange

account = Account.from_key(os.environ['HYPERLIQUID_PRIVATE_KEY'])
MAIN_WALLET = '0x97c465489243175580fcDe624c2ef640c1897a00'

BASE_URL = "https://api.hyperliquid-testnet.xyz"
info = Info(base_url=BASE_URL)
exchange = Exchange(wallet=account, base_url=BASE_URL)

print("=" * 60)
print("CLOSING ALL POSITIONS (Alternative method)")
print("=" * 60)

# Get current positions
state = info.user_state(MAIN_WALLET)
positions = state.get('assetPositions', [])

print(f"\nFound {len(positions)} positions to close:")
for pos in positions:
    p = pos.get('position', {})
    coin = p.get('coin', '')
    size = float(p.get('szi', 0))
    entry = p.get('entryPx', 0)
    print(f"\n{coin}: {size} @ ${entry}")
    
    # Close position by opening opposite direction
    if size > 0:
        print(f"  -> Selling {size} {coin} to close long...")
        result = exchange.market_open(name=coin, is_buy=False, sz=abs(size))
    else:
        print(f"  -> Buying {abs(size)} {coin} to close short...")
        result = exchange.market_open(name=coin, is_buy=True, sz=abs(size))
    print(f"  Result: {result}")

import time
time.sleep(2)

# Verify positions closed
state_after = info.user_state(MAIN_WALLET)
positions_after = state_after.get('assetPositions', [])
print(f"\n{'='*60}")
print(f"Positions after close: {len(positions_after)}")
if positions_after:
    for pos in positions_after:
        p = pos.get('position', {})
        print(f"  {p.get('coin')}: {p.get('szi')}")
else:
    print("  All positions closed successfully!")
