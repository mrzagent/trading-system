#!/usr/bin/env python3
"""Close all positions on main wallet"""
import os
import sys
sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from eth_account import Account

# Main wallet (the one with positions)
MAIN_KEY = "0x8c91e5e717c5f5196d9e4b658c374bdc18077c295e5728a1accf7ecebedbfe55"
main_account = Account.from_key(MAIN_KEY)
main_wallet = main_account.address

BASE_URL = "https://api.hyperliquid-testnet.xyz"

info = Info(base_url=BASE_URL)
exchange = Exchange(wallet=main_account, base_url=BASE_URL)

print("=" * 60)
print("CLOSING POSITIONS ON MAIN WALLET")
print("=" * 60)
print(f"Wallet: {main_wallet}")

# Get positions
state = info.user_state(main_wallet)
positions = state.get('assetPositions', [])

if not positions:
    print("No positions to close.")
    sys.exit(0)

print(f"\nFound {len(positions)} position(s):")
for pos in positions:
    p = pos.get('position', {})
    coin = p.get('coin')
    size = float(p.get('szi', 0))
    print(f"  {coin}: {size}")
    
    # Close position (market order opposite side)
    is_buy = size < 0  # If short, buy to close; if long, sell to close
    close_size = abs(size)
    
    print(f"  -> Closing with market order...")
    result = exchange.market_close(coin, size=round(close_size, 6))
    
    if result.get('status') == 'ok':
        statuses = result.get('response', {}).get('data', {}).get('statuses', [])
        if statuses and 'filled' in statuses[0]:
            print(f"     [OK] Closed!")
        elif statuses and 'error' in statuses[0]:
            print(f"     [ERROR] {statuses[0]['error']}")
        else:
            print(f"     Result: {result}")
    else:
        print(f"     [ERROR] {result}")

print("\n" + "=" * 60)
print("All positions closed!")
print("=" * 60)
