#!/usr/bin/env python3
"""Check if SDK caches connections or sessions"""
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

# Check if there's module-level caching
print("Checking for module-level caching...")
print(f"requests.Session class: {requests.Session}")

# Create fresh Exchange
account = Account.from_key(os.environ['HYPERLIQUID_PRIVATE_KEY'])
BASE_URL = "https://api.hyperliquid-testnet.xyz"

exchange1 = Exchange(wallet=account, base_url=BASE_URL)
print(f"\nExchange 1 session: {exchange1.session}")
print(f"Exchange 1 session headers: {exchange1.session.headers}")

# Create second Exchange with SAME wallet
exchange2 = Exchange(wallet=account, base_url=BASE_URL)
print(f"\nExchange 2 session: {exchange2.session}")
print(f"Same session? {exchange1.session is exchange2.session}")

# Check the actual request that gets sent
print("\n" + "=" * 60)
print("MONITORING ACTUAL REQUEST")
print("=" * 60)

# Monkey-patch session.post to see what's being sent
original_post = exchange1.session.post
def debug_post(url, **kwargs):
    print(f"\nREQUEST TO: {url}")
    if 'json' in kwargs:
        import json
        print(f"PAYLOAD: {json.dumps(kwargs['json'], indent=2)}")
    return original_post(url, **kwargs)

exchange1.session.post = debug_post

# Now place a tiny order
print("\nPlacing order...")
result = exchange1.market_open(name='BTC', is_buy=True, sz=0.0001)
print(f"\nResult: {result}")
