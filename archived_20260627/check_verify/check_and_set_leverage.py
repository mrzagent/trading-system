#!/usr/bin/env python3
"""Check positions and set leverage for future trades"""
import os
import sys

os.environ['HYPERLIQUID_WALLET'] = '0x89823A4f85cc8ef3A5574E8a56741A7b4562f288'
os.environ['HYPERLIQUID_PRIVATE_KEY'] = '0x5dc4eea052a2eac43ce453bbb116ae6c9f8a87daf3ccb455064cb9d0dbe62906'

sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

from eth_account import Account
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange

account = Account.from_key(os.environ['HYPERLIQUID_PRIVATE_KEY'])
MAIN_WALLET = '0x97c465489243175580fcDe624c2ef640c1897a00'

BASE_URL = "https://api.hyperliquid-testnet.xyz"
info = Info(base_url=BASE_URL)
exchange = Exchange(wallet=account, base_url=BASE_URL)

print("=" * 60)
print("CURRENT POSITIONS & LEVERAGE")
print("=" * 60)

state = info.user_state(MAIN_WALLET)
positions = state.get('assetPositions', [])

print(f"\nPositions: {len(positions)}")
for pos in positions:
    p = pos.get('position', {})
    coin = p.get('coin', '')
    size = p.get('szi', 0)
    entry = p.get('entryPx', 0)
    lev_type = p.get('leverage', {}).get('type', '?')
    lev_value = p.get('leverage', {}).get('value', '?')
    margin_used = p.get('marginUsed', 0)
    print(f"\n{coin}:")
    print(f"  Size: {size}")
    print(f"  Entry: ${entry}")
    print(f"  Leverage: {lev_value}x ({lev_type})")
    print(f"  Margin Used: ${margin_used}")

print("\n" + "=" * 60)
print("SETTING LEVERAGE FOR FUTURE TRADES")
print("=" * 60)

# Set leverage for SOL to 3x
print("\nSetting SOL leverage to 3x...")
try:
    result_sol = exchange.update_leverage(leverage=3, name='SOL', is_cross=True)
    print(f"SOL result: {result_sol}")
except Exception as e:
    print(f"Error: {e}")

# Set leverage for ETH to 10x  
print("\nSetting ETH leverage to 10x...")
try:
    result_eth = exchange.update_leverage(leverage=10, name='ETH', is_cross=True)
    print(f"ETH result: {result_eth}")
except Exception as e:
    print(f"Error: {e}")

print("\n" + "=" * 60)
print("Done! Future trades will use the new leverage settings.")
print("Note: Existing positions keep their current leverage.")
