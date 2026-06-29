#!/usr/bin/env python3
"""Debug the API query for agent wallet"""
import sys
sys.path.insert(0, r'D:\dev\trading')

from hyperliquid.info import Info

agent_wallet = '0x89823A4f85cc8ef3A5574E8a56741A7b4562f288'
agent_wallet_lower = agent_wallet.lower()

print(f'Original wallet: {agent_wallet}')
print(f'Lowercase wallet: {agent_wallet_lower}')
print()

info = Info(base_url='https://api.hyperliquid-testnet.xyz')

# Try original case
print('=== Query with original case ===')
state1 = info.user_state(agent_wallet)
print(f'Response: {state1}')
print()

# Try lowercase
print('=== Query with lowercase ===')
state2 = info.user_state(agent_wallet_lower)
print(f'Response: {state2}')
