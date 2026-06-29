#!/usr/bin/env python3
"""Prove SDK uses env var over wallet parameter"""
import os
import sys
sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

from eth_account import Account
from hyperliquid.exchange import Exchange

# Set .env to MAIN wallet (the bug scenario)
os.environ['HYPERLIQUID_WALLET'] = '0x97c465489243175580fcDe624c2ef640c1897a00'
os.environ['HYPERLIQUID_PRIVATE_KEY'] = '0x8c91e5e717c5f5196d9e4b658c374bdc18077c295e5728a1accf7ecebedbfe55'

# Create AGENT account (different from .env)
AGENT_KEY = '0x5dc4eea052a2eac43ce453bbb116ae6c9f8a87daf3ccb455064cb9d0dbe62906'
agent_account = Account.from_key(AGENT_KEY)

print("=" * 60)
print("SDK WALLET OVERRIDE BUG")
print("=" * 60)
print(f".env HYPERLIQUID_WALLET: {os.environ['HYPERLIQUID_WALLET']}")
print(f"Wallet passed to Exchange: {agent_account.address}")
print()

# Create exchange with AGENT wallet
BASE_URL = "https://api.hyperliquid-testnet.xyz"
exchange = Exchange(wallet=agent_account, base_url=BASE_URL)

print(f"Exchange.wallet.address: {exchange.wallet.address}")
print()

# The SDK's market_open method likely uses the env var, not the wallet
# Let's check by looking at what the SDK does internally

# Try to place a tiny order to see which wallet it uses
from hyperliquid.info import Info
info = Info(base_url=BASE_URL)

# Check agent wallet balance before
agent_state = info.user_state(agent_account.address)
agent_balance_before = float(agent_state.get('marginSummary', {}).get('accountValue', 0))
print(f"Agent wallet balance: ${agent_balance_before:.2f}")

# Check main wallet balance before
main_state = info.user_state(os.environ['HYPERLIQUID_WALLET'])
main_balance_before = float(main_state.get('marginSummary', {}).get('accountValue', 0))
print(f"Main wallet balance: ${main_balance_before:.2f}")

print("\n" + "=" * 60)
print("If SDK uses env var, trade will affect MAIN wallet")
print("If SDK uses wallet param, trade will affect AGENT wallet")
print("=" * 60)
