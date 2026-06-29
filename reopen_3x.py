#!/usr/bin/env python3
"""Reopen positions at 3x leverage"""
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
print("REOPENING POSITIONS AT 3X LEVERAGE")
print("=" * 60)

# Ensure leverage is set to 3x for both
print("\nSetting leverage to 3x for SOL and ETH...")
result_sol = exchange.update_leverage(leverage=3, name='SOL', is_cross=True)
result_eth = exchange.update_leverage(leverage=3, name='ETH', is_cross=True)
print(f"SOL leverage set: {result_sol.get('status')}")
print(f"ETH leverage set: {result_eth.get('status')}")

# Get current prices
mids = info.all_mids()
sol_price = float(mids.get('SOL', 0))
eth_price = float(mids.get('ETH', 0))

print(f"\nCurrent prices:")
print(f"  SOL: ${sol_price:,.2f}")
print(f"  ETH: ${eth_price:,.2f}")

# Open $50 positions at 3x
sol_sz = round(50 / sol_price, 2)
eth_sz = round(50 / eth_price, 4)

print(f"\nOpening positions (~$50 each at 3x):")
print(f"  SOL: {sol_sz} (~${sol_sz * sol_price:.2f})")
print(f"  ETH: {eth_sz} (~${eth_sz * eth_price:.2f})")

# Place orders
print("\n" + "=" * 60)
print("Placing orders...")

print("\n1. SOL market buy...")
result1 = exchange.market_open(name='SOL', is_buy=True, sz=sol_sz)
print(f"Result: {result1}")

print("\n2. ETH market buy...")
result2 = exchange.market_open(name='ETH', is_buy=True, sz=eth_sz)
print(f"Result: {result2}")

# Verify positions
import time
time.sleep(2)

print("\n" + "=" * 60)
print("Verifying new positions...")
state = info.user_state(MAIN_WALLET)
positions = state.get('assetPositions', [])

print(f"\nPositions: {len(positions)}")
for pos in positions:
    p = pos.get('position', {})
    coin = p.get('coin', '')
    size = p.get('szi', 0)
    entry = p.get('entryPx', 0)
    lev = p.get('leverage', {}).get('value', '?')
    print(f"  {coin}: {size} @ ${entry} ({lev}x)")
