#!/usr/bin/env python3
import os
import sys
sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

from hyperliquid.info import Info
info = Info(base_url='https://api.hyperliquid-testnet.xyz')

wallets = [
    '0x89823A4f85cc8ef3A5574E8a56741A7b4562f288',
    '0x97c465489243175580fcDe624c2ef640c1897a00',
]

print("POSITION CHECK AFTER TEST TRADE")
print("=" * 60)

for wallet in wallets:
    state = info.user_state(wallet)
    balance = float(state.get('marginSummary', {}).get('accountValue', 0))
    positions = state.get('assetPositions', [])
    
    print(f"\nWallet: {wallet}")
    print(f"  Balance: ${balance:.2f}")
    print(f"  Positions: {len(positions)}")
    for pos in positions:
        p = pos.get('position', {})
        coin = p.get('coin')
        size = p.get('szi')
        entry = p.get('entryPx')
        print(f"    {coin}: {size} @ ${entry}")
