#!/usr/bin/env python3
"""Check for module-level state in hyperliquid SDK"""
import os
import sys

# Clear env first
for key in ['HYPERLIQUID_WALLET', 'HYPERLIQUID_PRIVATE_KEY']:
    if key in os.environ:
        del os.environ[key]

# Set agent wallet
os.environ['HYPERLIQUID_WALLET'] = '0x89823A4f85cc8ef3A5574E8a56741A7b4562f288'
os.environ['HYPERLIQUID_PRIVATE_KEY'] = '0x5dc4eea052a2eac43ce453bbb116ae6c9f8a87daf3ccb455064cb9d0dbe62906'

sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

# Before importing hyperliquid, check env
print("Environment before import:")
print(f"  HYPERLIQUID_WALLET: {os.environ.get('HYPERLIQUID_WALLET')}")

# Import hyperliquid modules
import hyperliquid
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info

print("\nHyperliquid module location:", hyperliquid.__file__)

# Check if there's any global state
print("\nChecking hyperliquid.exchange module:")
import hyperliquid.exchange as ex_module
for name in dir(ex_module):
    if not name.startswith('_') and 'wallet' in name.lower():
        print(f"  {name}: {getattr(ex_module, name)}")

# Check Exchange class for class-level variables
print("\nExchange class attributes:")
for name in dir(Exchange):
    if not name.startswith('_'):
        try:
            val = getattr(Exchange, name)
            if not callable(val):
                print(f"  {name}: {val}")
        except:
            pass

# Now create an Exchange and check its internals
from eth_account import Account
account = Account.from_key(os.environ['HYPERLIQUID_PRIVATE_KEY'])
print(f"\nCreating Exchange with wallet: {account.address}")

ex = Exchange(wallet=account, base_url='https://api.hyperliquid-testnet.xyz')
print(f"Exchange.wallet.address: {ex.wallet.address}")

# Check if there's a sign method we can inspect
print(f"\nExchange.sign method: {ex.sign}")
if hasattr(ex, 'sign'):
    import inspect
    print(f"Sign signature: {inspect.signature(ex.sign)}")
