#!/usr/bin/env python3
"""Place $10 ETH trade on agent wallet - WITH VAULT ADDRESS"""
import os
import sys

# Force agent wallet env
os.environ['HYPERLIQUID_WALLET'] = '0x89823A4f85cc8ef3A5574E8a56741A7b4562f288'
os.environ['HYPERLIQUID_PRIVATE_KEY'] = '0x5dc4eea052a2eac43ce453bbb116ae6c9f8a87daf3ccb455064cb9d0dbe62906'

sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

from eth_account import Account
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange

# Create account
account = Account.from_key(os.environ['HYPERLIQUID_PRIVATE_KEY'])
AGENT_WALLET = account.address
MASTER_WALLET = '0x97c465489243175580fcDe624c2ef640c1897a00'  # Main/master wallet

print("=" * 60)
print("PLACING $10 ETH TRADE - WITH VAULT ADDRESS")
print("=" * 60)
print(f"Agent Wallet: {AGENT_WALLET}")
print(f"Master Wallet: {MASTER_WALLET}")

BASE_URL = "https://api.hyperliquid-testnet.xyz"
info = Info(base_url=BASE_URL)

# Try Exchange with vault address
print("\nMethod 1: Exchange with vault_address parameter")
try:
    exchange = Exchange(wallet=account, base_url=BASE_URL, vault_address=MASTER_WALLET)
    print("Exchange created with vault_address")
except Exception as e:
    print(f"Error with vault_address: {e}")
    print("Falling back to standard Exchange...")
    exchange = Exchange(wallet=account, base_url=BASE_URL)

# Check balance before
state = info.user_state(AGENT_WALLET)
balance_before = float(state.get('marginSummary', {}).get('accountValue', 0))
pos_count_before = len(state.get('assetPositions', []))
print(f"\nAgent Balance: ${balance_before:.2f}")
print(f"Positions before: {pos_count_before}")

# Get ETH price and calculate size for $10 (safer given low balance)
mids = info.all_mids()
eth_price = float(mids.get('ETH', 0))
sz = round(10 / eth_price, 4)  # $10 notional, 4 decimals

print(f"\nETH Price: ${eth_price:,.2f}")
print(f"Size: {sz} ETH (~${sz * eth_price:.2f})")

# Place market buy order
print("\nPlacing ETH market buy order...")
result = exchange.market_open(name='ETH', is_buy=True, sz=sz)
print(f"Result: {result}")

# Check after
print("\n" + "=" * 60)
print("Verifying position...")

state_after = info.user_state(AGENT_WALLET)
balance_after = float(state_after.get('marginSummary', {}).get('accountValue', 0))
pos_count_after = len(state_after.get('assetPositions', []))
print(f"Balance after: ${balance_after:.2f}")
print(f"Positions after: {pos_count_after}")

for pos in state_after.get('assetPositions', []):
    p = pos.get('position', {})
    coin = p.get('coin', '')
    print(f"  {coin}: {p.get('szi')} @ ${p.get('entryPx')}")

if pos_count_after > pos_count_before:
    print("\n[OK] Trade landed on AGENT wallet!")
else:
    print("\n[CHECK] Position count unchanged - checking fills...")
    fills = info.user_fills(AGENT_WALLET)
    print(f"Total fills: {len(fills)}")
    for fill in fills:
        print(f"  {fill.get('coin')} {fill.get('dir')} {fill.get('sz')} @ ${fill.get('px')}")
