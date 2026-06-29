#!/usr/bin/env python3
"""Check for session/auth caching"""
import os
import sys

# Fresh environment
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

# Create a completely fresh Exchange with a new Session
import requests

# First, let's clear any connection pools
if hasattr(requests, 'Session'):
    # Create a fresh session
    fresh_session = requests.Session()
    
account = Account.from_key(os.environ['HYPERLIQUID_PRIVATE_KEY'])
print(f"Using wallet: {account.address}")

# Create exchange but we'll replace its session
BASE_URL = "https://api.hyperliquid-testnet.xyz"
exchange = Exchange(wallet=account, base_url=BASE_URL)

# Replace the session with a completely fresh one
exchange.session = fresh_session

# Check positions before
info = Info(base_url=BASE_URL)
agent_state = info.user_state(account.address)
print(f"Agent positions before: {len(agent_state.get('assetPositions', []))}")

main_wallet = '0x97c465489243175580fcDe624c2ef640c1897a00'
main_state = info.user_state(main_wallet)
main_positions_before = len(main_state.get('assetPositions', []))
print(f"Main positions before: {main_positions_before}")

# Place a tiny order
print("\nPlacing 0.0001 BTC order...")
result = exchange.market_open(name='BTC', is_buy=True, sz=0.0001)
print(f"Result: {result}")

# Check positions after
print("\nChecking positions after...")
agent_state = info.user_state(account.address)
agent_positions_after = len(agent_state.get('assetPositions', []))
print(f"Agent positions after: {agent_positions_after}")

main_state = info.user_state(main_wallet)
main_positions_after = len(main_state.get('assetPositions', []))
print(f"Main positions after: {main_positions_after}")

if agent_positions_after > len(agent_state.get('assetPositions', [])):
    print("\n[OK] Trade went to AGENT wallet!")
elif main_positions_after > main_positions_before:
    print("\n[FAIL] Trade went to MAIN wallet again!")
else:
    print("\n[?] No position change detected")
