#!/usr/bin/env python3
"""Check MAIN wallet for positions (agent trades show up here)"""
import sys
sys.path.insert(0, r'D:\dev\trading')

from hyperliquid.info import Info

MAIN_WALLET = '0x97c465489243175580fcDe624c2ef640c1897a00'
AGENT_WALLET = '0x89823A4f85cc8ef3A5574E8a56741A7b4562f288'

info = Info(base_url='https://api.hyperliquid-testnet.xyz')

print("=" * 60)
print("CHECKING MAIN WALLET FOR AGENT TRADES")
print("=" * 60)

# Check main wallet
state = info.user_state(MAIN_WALLET)
print(f"\nMain Wallet ({MAIN_WALLET}):")
print(f"  Account Value: ${float(state.get('marginSummary', {}).get('accountValue', 0)):.2f}")
print(f"  Positions: {len(state.get('assetPositions', []))}")

for pos in state.get('assetPositions', []):
    p = pos.get('position', {})
    coin = p.get('coin', '')
    size = p.get('szi', 0)
    entry = p.get('entryPx', 0)
    print(f"    {coin}: {size} @ ${entry}")

# Check fills on main wallet
fills = info.user_fills(MAIN_WALLET)
print(f"\n  Fills ({len(fills)} total):")
for fill in fills[-5:]:
    print(f"    {fill.get('coin')} {fill.get('dir')} {fill.get('sz')} @ ${fill.get('px')} (OID: {fill.get('oid')})")

print("\n" + "=" * 60)
print("AGENT WALLET (for reference):")
agent_state = info.user_state(AGENT_WALLET)
print(f"  Account Value: ${float(agent_state.get('marginSummary', {}).get('accountValue', 0)):.2f}")
print(f"  Positions: {len(agent_state.get('assetPositions', []))}")
