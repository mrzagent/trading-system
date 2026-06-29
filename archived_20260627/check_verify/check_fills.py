#!/usr/bin/env python3
"""Check fills for agent wallet"""
import sys
sys.path.insert(0, r'D:\dev\trading')

import os
os.environ['HYPERLIQUID_WALLET'] = '0x89823A4f85cc8ef3A5574E8a56741A7b4562f288'
os.environ['HYPERLIQUID_PRIVATE_KEY'] = '0x5dc4eea052a2eac43ce453bbb116ae6c9f8a87daf3ccb455064cb9d0dbe62906'

from hyperliquid.info import Info
from eth_account import Account

account = Account.from_key(os.environ['HYPERLIQUID_PRIVATE_KEY'])
wallet = account.address

info = Info(base_url='https://api.hyperliquid-testnet.xyz')

print(f"Checking fills for: {wallet}")
print()

# Get user fills
fills = info.user_fills(wallet)
print(f"Total fills: {len(fills)}")
print()

# Show last 5 fills
for fill in fills[-5:]:
    print(f"  {fill}")
