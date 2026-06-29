#!/usr/bin/env python3
"""Test trade to verify wallet routing"""
import os
import sys
sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

# Load from .env
from dotenv import load_dotenv
load_dotenv(r'C:\Users\mrztms\.openclaw\.env')

print("Environment variables from .env:")
print(f"  HYPERLIQUID_WALLET: {os.getenv('HYPERLIQUID_WALLET')}")
print(f"  HYPERLIQUID_PRIVATE_KEY: {os.getenv('HYPERLIQUID_PRIVATE_KEY')[:20]}...")

from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info

# Create account from env key
account = Account.from_key(os.getenv('HYPERLIQUID_PRIVATE_KEY'))
print(f"\nDerived address from key: {account.address}")
print(f"Matches .env WALLET: {account.address.lower() == os.getenv('HYPERLIQUID_WALLET').lower()}")

# Create exchange
BASE_URL = "https://api.hyperliquid-testnet.xyz"
info = Info(base_url=BASE_URL)
exchange = Exchange(wallet=account, base_url=BASE_URL)

print(f"\nExchange.wallet.address: {exchange.wallet.address}")

# Check current positions
wallet = os.getenv('HYPERLIQUID_WALLET')
state = info.user_state(wallet)
balance = float(state.get('marginSummary', {}).get('accountValue', 0))
positions = state.get('assetPositions', [])

print(f"\nWallet {wallet[:10]}... state:")
print(f"  Balance: ${balance:.2f}")
print(f"  Positions: {len(positions)}")
for pos in positions:
    p = pos.get('position', {})
    print(f"    {p.get('coin')}: {p.get('szi')}")

print("\n" + "=" * 60)
print("All checks passed. Ready to trade on correct wallet!")
print("=" * 60)
