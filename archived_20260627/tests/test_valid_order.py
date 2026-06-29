#!/usr/bin/env python3
"""Test with valid order size"""
import os
import sys

for key in ['HYPERLIQUID_WALLET', 'HYPERLIQUID_PRIVATE_KEY']:
    if key in os.environ:
        del os.environ[key]

os.environ['HYPERLIQUID_WALLET'] = '0x89823A4f85cc8ef3A5574E8a56741A7b4562f288'
os.environ['HYPERLIQUID_PRIVATE_KEY'] = '0x5dc4eea052a2eac43ce453bbb116ae6c9f8a87daf3ccb455064cb9d0dbe62906'

sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
import requests

account = Account.from_key(os.environ['HYPERLIQUID_PRIVATE_KEY'])
print(f"Using wallet: {account.address}")

BASE_URL = "https://api.hyperliquid-testnet.xyz"
info = Info(base_url=BASE_URL)
exchange = Exchange(wallet=account, base_url=BASE_URL)
exchange.session = requests.Session()

# Get BTC price
mids = info.all_mids()
btc_price = float(mids.get('BTC', 0))
print(f"BTC Price: ${btc_price:,.2f}")

# Calculate size for $20 notional
sz = round(20 / btc_price, 5)
print(f"Order size: {sz} BTC ($20 notional)")

# Check positions before
main_wallet = '0x97c465489243175580fcDe624c2ef640c1897a00'
main_state = info.user_state(main_wallet)
main_btc_before = 0
for pos in main_state.get('assetPositions', []):
    if pos.get('position', {}).get('coin') == 'BTC':
        main_btc_before = float(pos.get('position', {}).get('szi', 0))
print(f"\nMain BTC before: {main_btc_before}")

agent_state = info.user_state(account.address)
agent_btc_before = 0
for pos in agent_state.get('assetPositions', []):
    if pos.get('position', {}).get('coin') == 'BTC':
        agent_btc_before = float(pos.get('position', {}).get('szi', 0))
print(f"Agent BTC before: {agent_btc_before}")

# Place order
print(f"\nPlacing order...")
result = exchange.market_open(name='BTC', is_buy=True, sz=sz)
print(f"Result: {result}")

# Check positions after
main_state = info.user_state(main_wallet)
main_btc_after = 0
for pos in main_state.get('assetPositions', []):
    if pos.get('position', {}).get('coin') == 'BTC':
        main_btc_after = float(pos.get('position', {}).get('szi', 0))

agent_state = info.user_state(account.address)
agent_btc_after = 0
for pos in agent_state.get('assetPositions', []):
    if pos.get('position', {}).get('coin') == 'BTC':
        agent_btc_after = float(pos.get('position', {}).get('szi', 0))

print(f"\nMain BTC after: {main_btc_after}")
print(f"Agent BTC after: {agent_btc_after}")

if agent_btc_after > agent_btc_before:
    print(f"\n[OK] Trade went to AGENT! Added {agent_btc_after - agent_btc_before} BTC")
elif main_btc_after > main_btc_before:
    print(f"\n[FAIL] Trade went to MAIN! Added {main_btc_after - main_btc_before} BTC")
else:
    print("\n[?] No change")
