#!/usr/bin/env python3
"""Debug SDK signing and routing"""
import os
import sys

# Clear and set env
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
import inspect

account = Account.from_key(os.environ['HYPERLIQUID_PRIVATE_KEY'])
print(f"Account address: {account.address}")
print(f"Env WALLET: {os.environ['HYPERLIQUID_WALLET']}")

BASE_URL = "https://api.hyperliquid-testnet.xyz"
exchange = Exchange(wallet=account, base_url=BASE_URL)

print(f"\nExchange.wallet.address: {exchange.wallet.address}")
print(f"Exchange.vault_address: {exchange.vault_address}")
print(f"Exchange.account_address: {exchange.account_address}")

# Check the market_open method signature
print(f"\nExchange.market_open signature:")
sig = inspect.signature(exchange.market_open)
print(f"  {sig}")

# Check if there's a default vault or account being used
print("\nExchange attributes:")
for attr in ['wallet', 'vault_address', 'account_address', 'base_url']:
    val = getattr(exchange, attr, None)
    print(f"  {attr}: {val}")

# Check the source of the market_open method
print(f"\nmarket_open method location: {exchange.market_open.__module__}")

# Try to see what action is being built
print("\n" + "=" * 60)
print("Let's manually construct an order and see what happens")
print("=" * 60)

# Get the action that would be signed
import json
action = {
    "type": "order",
    "orders": [{"coin": "BTC", "is_buy": True, "sz": "0.001", "limit_px": "65000", "order_type": {"market": {}}, "reduce_only": False}],
    "grouping": "na",
    "builder": None
}

from eth_account.messages import encode_defunct
message_str = json.dumps(action, separators=(',', ':'))
message = encode_defunct(text=message_str)
signed = account.sign_message(message)

print(f"Message: {message_str}")
print(f"Signed by: {account.address}")
print(f"Signature: {signed.signature.hex()[:40]}...")

# The signature proves the order is signed by agent wallet
# But somehow it's being credited to main wallet
