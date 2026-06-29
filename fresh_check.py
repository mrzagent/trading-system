#!/usr/bin/env python3
"""Fresh check using direct SDK with no caching"""
import sys
sys.path.insert(0, r'D:\dev\trading')

# Fresh import - no cache
import importlib
import hyperliquid.info
importlib.reload(hyperliquid.info)

from hyperliquid.info import Info

agent_wallet = "0x89823A4f85cc8ef3A5574E8a56741A7b4562f288"

print(f"Checking wallet: {agent_wallet}")
print(f"Time: {__import__('time').time()}")
print()

# Create fresh Info instance
info = Info(base_url="https://api.hyperliquid-testnet.xyz")

# Get user state
state = info.user_state(agent_wallet)
print(f"Full response:")
for key, value in state.items():
    print(f"  {key}: {value}")

print()
print(f"Parsed:")
print(f"  accountValue: {state.get('marginSummary', {}).get('accountValue')}")
print(f"  withdrawable: {state.get('withdrawable')}")
print(f"  assetPositions: {len(state.get('assetPositions', []))}")
