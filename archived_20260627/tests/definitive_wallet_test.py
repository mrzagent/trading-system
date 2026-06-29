#!/usr/bin/env python3
"""
Definitive test to verify which wallet orders are placed from.
Places a real order and checks the user state before/after.
"""
import os
import sys
import time

# Clear any existing env vars
for key in ['HYPERLIQUID_PRIVATE_KEY', 'HYPERLIQUID_WALLET']:
    if key in os.environ:
        del os.environ[key]

# AGENT WALLET - The one we want to use
AGENT_PRIVATE_KEY = '0x5dc4eea052a2eac43ce453bbb116ae6c9f8a87daf3ccb455064cb9d0dbe62906'
AGENT_WALLET = '0x89823A4f85cc8ef3A5574E8a56741A7b4562f288'

# MAIN WALLET - The one trades are incorrectly going to  
MAIN_WALLET = '0x97c465489243175580fcDe624c2ef640c1897a00'

from eth_account import Account
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange

BASE_URL = "https://api.hyperliquid-testnet.xyz"

print("=" * 70)
print("DEFINITIVE WALLET ROUTING TEST")
print("=" * 70)

# Create agent account
agent_account = Account.from_key(AGENT_PRIVATE_KEY)
print(f"\nUsing Account: {agent_account.address}")
print(f"Expected:      {AGENT_WALLET}")
print(f"Match:         {agent_account.address.lower() == AGENT_WALLET.lower()}")

# Create exchange
info = Info(base_url=BASE_URL, skip_ws=True)
exchange = Exchange(wallet=agent_account, base_url=BASE_URL)

# Get current state BEFORE order
print("\n--- STATE BEFORE ORDER ---")
mids = info.all_mids()
btc_price = float(mids.get('BTC', 0))
print(f"BTC Price: ${btc_price:,.2f}")

agent_state_before = info.user_state(AGENT_WALLET)
main_state_before = info.user_state(MAIN_WALLET)

agent_positions_before = {p['position']['coin']: p['position'] for p in agent_state_before.get('assetPositions', [])}
main_positions_before = {p['position']['coin']: p['position'] for p in main_state_before.get('assetPositions', [])}

print(f"\nAgent Wallet ({AGENT_WALLET[:12]}...):")
print(f"  Balance: ${float(agent_state_before.get('marginSummary', {}).get('accountValue', 0)):.2f}")
print(f"  Positions: {list(agent_positions_before.keys())}")

print(f"\nMain Wallet ({MAIN_WALLET[:12]}...):")
print(f"  Balance: ${float(main_state_before.get('marginSummary', {}).get('accountValue', 0)):.2f}")
print(f"  Positions: {list(main_positions_before.keys())}")

# Calculate order size - need at least $10 notional
# Let's do $15 notional to be safe
notional = 15.0
btc_size = round(notional / btc_price, 5)
print(f"\n--- PLACING ORDER ---")
print(f"Order: BUY {btc_size} BTC (~${notional} notional)")
print(f"Exchange.wallet.address: {exchange.wallet.address}")

# Place the order
result = exchange.market_open(
    name='BTC',
    is_buy=True,
    sz=btc_size
)

print(f"\nOrder Result:")
print(f"  Status: {result.get('status')}")

if result.get('status') == 'ok':
    statuses = result.get('response', {}).get('data', {}).get('statuses', [])
    if statuses:
        if 'filled' in statuses[0]:
            fill = statuses[0]['filled']
            print(f"  Filled: {fill.get('totalSz')} @ ${fill.get('avgPx')}")
            print(f"  Position Id: {fill.get('positionId')}")
        elif 'error' in statuses[0]:
            print(f"  Error: {statuses[0]['error']}")
        else:
            print(f"  Response: {statuses[0]}")

# Wait a moment for state to update
print("\nWaiting 2 seconds for state update...")
time.sleep(2)

# Get state AFTER order
print("\n--- STATE AFTER ORDER ---")
agent_state_after = info.user_state(AGENT_WALLET)
main_state_after = info.user_state(MAIN_WALLET)

agent_positions_after = {p['position']['coin']: p['position'] for p in agent_state_after.get('assetPositions', [])}
main_positions_after = {p['position']['coin']: p['position'] for p in main_state_after.get('assetPositions', [])}

print(f"\nAgent Wallet ({AGENT_WALLET[:12]}...):")
print(f"  Balance: ${float(agent_state_after.get('marginSummary', {}).get('accountValue', 0)):.2f}")
print(f"  Positions: {list(agent_positions_after.keys())}")
if 'BTC' in agent_positions_after:
    pos = agent_positions_after['BTC']
    print(f"  BTC Position: {pos.get('szi')} @ ${pos.get('entryPx')}")

print(f"\nMain Wallet ({MAIN_WALLET[:12]}...):")
print(f"  Balance: ${float(main_state_after.get('marginSummary', {}).get('accountValue', 0)):.2f}")
print(f"  Positions: {list(main_positions_after.keys())}")
if 'BTC' in main_positions_after:
    pos = main_positions_after['BTC']
    print(f"  BTC Position: {pos.get('szi')} @ ${pos.get('entryPx')}")

# Determine where the order went
print("\n" + "=" * 70)
print("RESULT")
print("=" * 70)

agent_btc_before = float(agent_positions_before.get('BTC', {}).get('szi', 0))
agent_btc_after = float(agent_positions_after.get('BTC', {}).get('szi', 0))
main_btc_before = float(main_positions_before.get('BTC', {}).get('szi', 0))
main_btc_after = float(main_positions_after.get('BTC', {}).get('szi', 0))

print(f"Agent BTC: {agent_btc_before} -> {agent_btc_after} (change: {agent_btc_after - agent_btc_before})")
print(f"Main BTC:  {main_btc_before} -> {main_btc_after} (change: {main_btc_after - main_btc_before})")

if agent_btc_after > agent_btc_before:
    print("\n✓ ORDER WENT TO AGENT WALLET (CORRECT!)")
elif main_btc_after > main_btc_before:
    print("\n✗ ORDER WENT TO MAIN WALLET (BUG CONFIRMED!)")
    print(f"\nThe Exchange class is NOT using the provided wallet!")
    print(f"Expected to use: {AGENT_WALLET}")
    print(f"But order landed on: {MAIN_WALLET}")
else:
    print("\n? NO CHANGE DETECTED - order may have failed or not been placed")

print("=" * 70)
