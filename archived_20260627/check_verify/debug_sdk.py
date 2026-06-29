#!/usr/bin/env python3
"""Verify SDK wallet override issue"""
import os
import sys
sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

from eth_account import Account
from hyperliquid.exchange import Exchange

# Set .env to agent wallet
os.environ['HYPERLIQUID_WALLET'] = '0x89823A4f85cc8ef3A5574E8a56741A7b4562f288'
os.environ['HYPERLIQUID_PRIVATE_KEY'] = '0x5dc4eea052a2eac43ce453bbb116ae6c9f8a87daf3ccb455064cb9d0dbe62906'

# Create account from key
account = Account.from_key(os.environ['HYPERLIQUID_PRIVATE_KEY'])
print(f"Account from key: {account.address}")
print(f".env WALLET: {os.environ['HYPERLIQUID_WALLET']}")

# Create exchange with this account
BASE_URL = "https://api.hyperliquid-testnet.xyz"
exchange = Exchange(wallet=account, base_url=BASE_URL)

# Check what the exchange thinks its wallet is
print(f"\nExchange.wallet: {exchange.wallet}")
print(f"Exchange.wallet.address: {exchange.wallet.address}")

# Check if there's a vault_address being used
print(f"Exchange.vault_address: {exchange.vault_address}")
print(f"Exchange.account_address: {exchange.account_address}")

# Now check if SDK uses environment variables
print("\n--- Checking SDK internals ---")

# Look at the exchange's internal state
import inspect
sig = inspect.signature(Exchange.__init__)
print(f"Exchange.__init__ signature: {sig}")

# Check if SDK reads from env
for attr in ['wallet', 'vault_address', 'account_address']:
    val = getattr(exchange, attr, None)
    print(f"exchange.{attr} = {val}")
