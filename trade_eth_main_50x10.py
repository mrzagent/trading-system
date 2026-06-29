#!/usr/bin/env python3
"""Place $50 ETH 10x long on MAIN account"""
import os
import sys

# Main wallet
os.environ['HYPERLIQUID_WALLET'] = '0x97c465489243175580fcDe624c2ef640c1897a00'
os.environ['HYPERLIQUID_PRIVATE_KEY'] = '0x6f3f9e9f8a3b2c1d0e5f4a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7'

sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

from eth_account import Account
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange

account = Account.from_key(os.environ['HYPERLIQUID_PRIVATE_KEY'])
WALLET = account.address

print("=" * 60)
print("PLACING $50 ETH 10X LONG ON MAIN ACCOUNT")
print("=" * 60)
print(f"Wallet: {WALLET}")

BASE_URL = "https://api.hyperliquid-testnet.xyz"
info = Info(base_url=BASE_URL)
exchange = Exchange(wallet=account, base_url=BASE_URL)

# Check balance before
state = info.user_state(WALLET)
balance_before = float(state.get('marginSummary', {}).get('accountValue', 0))
print(f"Balance: ${balance_before:.2f}")

# Get ETH price and calculate size for $50 notional at 10x leverage
# For 10x, we need $5 margin, but the notional is still $50
mids = info.all_mids()
eth_price = float(mids.get('ETH', 0))
sz = round(50 / eth_price, 4)

print(f"\nETH Price: ${eth_price:,.2f}")
print(f"Size: {sz} ETH (notional: ~${sz * eth_price:.2f})")
print(f"Leverage: 10x (margin required: ~${sz * eth_price / 10:.2f})")

# Place market buy order with 10x leverage
print("\nPlacing ETH market buy order at 10x...")
result = exchange.market_open(name='ETH', is_buy=True, sz=sz)
print(f"Result: {result}")

# Check position after
if result.get('status') == 'ok':
    print("\n" + "=" * 60)
    print("Checking position...")
    import time
    time.sleep(2)
    
    state_after = info.user_state(WALLET)
    balance_after = float(state_after.get('marginSummary', {}).get('accountValue', 0))
    positions = state_after.get('assetPositions', [])
    
    print(f"Balance after: ${balance_after:.2f}")
    print(f"Positions: {len(positions)}")
    
    for pos in positions:
        p = pos.get('position', {})
        coin = p.get('coin', '')
        size = p.get('szi', 0)
        entry = p.get('entryPx', 0)
        leverage = p.get('leverage', {})
        print(f"  {coin}: {size} @ ${entry} (leverage: {leverage})")
