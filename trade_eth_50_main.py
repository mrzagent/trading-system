#!/usr/bin/env python3
"""Place $50 ETH 10x long - uses agent key (routes to main)"""
import os
import sys

# Agent wallet (routes to main account)
os.environ['HYPERLIQUID_WALLET'] = '0x89823A4f85cc8ef3A5574E8a56741A7b4562f288'
os.environ['HYPERLIQUID_PRIVATE_KEY'] = '0x5dc4eea052a2eac43ce453bbb116ae6c9f8a87daf3ccb455064cb9d0dbe62906'

sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

from eth_account import Account
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange

account = Account.from_key(os.environ['HYPERLIQUID_PRIVATE_KEY'])
AGENT_WALLET = account.address
MAIN_WALLET = '0x97c465489243175580fcDe624c2ef640c1897a00'

print("=" * 60)
print("PLACING $50 ETH 10X LONG")
print("=" * 60)
print(f"Signing with: {AGENT_WALLET}")
print(f"(Routes to main: {MAIN_WALLET})")

BASE_URL = "https://api.hyperliquid-testnet.xyz"
info = Info(base_url=BASE_URL)
exchange = Exchange(wallet=account, base_url=BASE_URL)

# Check main account balance
state = info.user_state(MAIN_WALLET)
balance = float(state.get('marginSummary', {}).get('accountValue', 0))
print(f"Main balance: ${balance:.2f}")

# Get ETH price
mids = info.all_mids()
eth_price = float(mids.get('ETH', 0))
sz = round(50 / eth_price, 4)

print(f"\nETH Price: ${eth_price:,.2f}")
print(f"Size: {sz} ETH (notional: ~${sz * eth_price:.2f})")

# Place market buy
print("\nPlacing order...")
result = exchange.market_open(name='ETH', is_buy=True, sz=sz)
print(f"Result: {result}")

# Verify on main
if result.get('status') == 'ok' and 'filled' in str(result):
    import time
    time.sleep(2)
    
    print("\n" + "=" * 60)
    print("Verifying on main account...")
    
    state_after = info.user_state(MAIN_WALLET)
    positions = state_after.get('assetPositions', [])
    
    print(f"Positions: {len(positions)}")
    for pos in positions:
        p = pos.get('position', {})
        coin = p.get('coin', '')
        size = p.get('szi', 0)
        entry = p.get('entryPx', 0)
        lev = p.get('leverage', {}).get('value', '?')
        print(f"  {coin}: {size} @ ${entry} ({lev}x)")
    
    # Check fills
    fills = info.user_fills(MAIN_WALLET)
    latest = fills[-1] if fills else None
    if latest:
        print(f"\nLatest fill: {latest.get('coin')} {latest.get('dir')} {latest.get('sz')} @ ${latest.get('px')}")
