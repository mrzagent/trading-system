from hyperliquid.info import Info
info = Info(base_url='https://api.hyperliquid-testnet.xyz')
state = info.user_state('0x89823A4f85cc8ef3A5574E8a56741A7b4562f288')
positions = state.get('assetPositions', [])
print(f'Positions found: {len(positions)}')
for p in positions:
    pos = p['position']
    print(f"  {pos['coin']}: {pos['szi']} @ {pos.get('entryPx', 'N/A')}")
