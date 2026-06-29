#!/usr/bin/env python3
"""Debug script to trace wallet routing issue"""
import os
import sys
sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

# FORCE CORRECT AGENT WALLET KEY
os.environ['HYPERLIQUID_PRIVATE_KEY'] = '0x5dc4eea052a2eac43ce453bbb116ae6c9f8a87daf3ccb455064cb9d0dbe62906'

from eth_account import Account
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange

# Test both wallets
AGENT_KEY = '0x5dc4eea052a2eac43ce453bbb116ae6c9f8a87daf3ccb455064cb9d0dbe62906'
MAIN_KEY = '0x8c91e5e717c5f5196d9e4b658c374bdc18077c295e5728a1accf7ecebedbfe55'

agent_account = Account.from_key(AGENT_KEY)
main_account = Account.from_key(MAIN_KEY)

print("=" * 60)
print("WALLET VERIFICATION")
print("=" * 60)
print(f"Agent Key: {AGENT_KEY[:20]}...")
print(f"Agent Address: {agent_account.address}")
print()
print(f"Main Key: {MAIN_KEY[:20]}...")
print(f"Main Address: {main_account.address}")
print()

BASE_URL = "https://api.hyperliquid-testnet.xyz"
info = Info(base_url=BASE_URL)

# Check balances
print("=" * 60)
print("BALANCES")
print("=" * 60)

agent_state = info.user_state(agent_account.address)
agent_balance = float(agent_state.get('marginSummary', {}).get('accountValue', 0))
print(f"Agent ({agent_account.address[:10]}...): ${agent_balance:.2f}")

main_state = info.user_state(main_account.address)
main_balance = float(main_state.get('marginSummary', {}).get('accountValue', 0))
print(f"Main ({main_account.address[:10]}...): ${main_balance:.2f}")

# Check positions
print()
print("=" * 60)
print("POSITIONS")
print("=" * 60)

agent_positions = agent_state.get('assetPositions', [])
print(f"Agent positions: {len(agent_positions)}")
for pos in agent_positions:
    p = pos.get('position', {})
    print(f"  {p.get('coin')}: {p.get('szi')}")

main_positions = main_state.get('assetPositions', [])
print(f"Main positions: {len(main_positions)}")
for pos in main_positions:
    p = pos.get('position', {})
    print(f"  {p.get('coin')}: {p.get('szi')}")

print()
print("=" * 60)
print("SDK EXCHANGE TEST")
print("=" * 60)

# Create exchange with agent wallet
exchange = Exchange(wallet=agent_account, base_url=BASE_URL)

# Print what the exchange thinks its wallet is
print(f"Exchange created with wallet: {agent_account.address}")
print(f"Exchange wallet address attr: {getattr(exchange, 'wallet_address', 'N/A')}")

# Inspect the exchange object
print("\nExchange object attributes:")
for attr in dir(exchange):
    if not attr.startswith('_'):
        val = getattr(exchange, attr)
        if not callable(val):
            print(f"  {attr}: {val}")
