#!/usr/bin/env python3
"""Place $50 SOL 3x long - uses agent key (routes to main)"""
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

print("=" * 60)
print("PLACING $50 SOL 3X LONG")
print("=" * 60)

BASE_URL = "https://api.hyperliquid-testnet.xyz"
info = Info(base_url=BASE_URL)
exchange = Exchange(wallet=account, base_url=BASE_URL)

# Check current positions
state = info.user_state(MAIN_WALLET)
positions = state.get('assetPositions', [])
print(f"Current positions: {len(positions)}")
for pos in positions:
    p = pos.get('position', {})
    print(f"  {p.get('coin')}: {p.get('szi')} @ ${p.get('entryPx')}")

# Get SOL price and calculate size
mids = info.all_mids()
sol_price = float(mids.get('SOL', 0))
sz = round(50 / sol_price, 2)  # SOL has szDecimals=2

print(f"\nSOL Price: ${sol_price:,.2f}")
print(f"Size: {sz} SOL (notional: ~${sz * sol_price:.2f})")

# Place market buy
print("\nPlacing order...")
result = exchange.market_open(name='SOL', is_buy=True, sz=sz)
print(f"Result: {result}")

# Verify
if result.get('status') == 'ok' and 'filled' in str(result):
    import time
    time.sleep(2)
    
    print("\n" + "=" * 60)
    print("Verifying on main account...")
    
    state_after = info.user_state(MAIN_WALLET)
    positions_after = state_after.get('assetPositions', [])
    
    print(f"Positions: {len(positions_after)}")
    for pos in positions_after:
        p = pos.get('position', {})
        coin = p.get('coin', '')
        size = p.get('szi', 0)
        entry = p.get('entryPx', 0)
        lev = p.get('leverage', {}).get('value', '?')
        print(f"  {coin}: {size} @ ${entry} ({lev}x)")
