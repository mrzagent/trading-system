#!/usr/bin/env python3
"""Close the SOL position and cancel all orders"""
import sys
import os

sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

from dotenv import load_dotenv
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants
from eth_account import Account

load_dotenv(r'C:\Users\mrztms\.openclaw\.env')

wallet_address = os.getenv('HYPERLIQUID_WALLET')
private_key = os.getenv('HYPERLIQUID_PRIVATE_KEY')

account = Account.from_key(private_key)
exchange = Exchange(account, base_url=constants.TESTNET_API_URL)
info = Info(constants.TESTNET_API_URL)

print("=" * 60)
print("CLOSING SOL POSITION")
print("=" * 60)

# Get current position
user_state = info.user_state(wallet_address)
positions = user_state.get('assetPositions', [])

sol_pos = None
for pos_data in positions:
    pos = pos_data.get('position', {})
    if pos.get('coin') == 'SOL':
        sol_pos = pos
        break

if not sol_pos:
    print("No SOL position found")
else:
    size = float(sol_pos.get('szi', 0))
    entry_px = float(sol_pos.get('entryPx', 0))
    
    print(f"Position: {size} SOL @ ${entry_px:.2f}")
    
    # Cancel all open orders first
    open_orders = user_state.get('openOrders', [])
    for order in open_orders:
        if order.get('coin') == 'SOL':
            oid = order.get('oid')
            if oid:
                result = exchange.cancel('SOL', oid)
                print(f"Cancelled order {oid}: {result.get('status')}")
    
    # Close position (market order)
    if size != 0:
        is_buy = size < 0  # If short, buy to close; if long, sell to close
        
        # Get current price for limit
        mids = info.all_mids()
        current_px = float(mids.get('SOL', 0))
        
        # Use market-able limit (0.5% slippage)
        limit_px = round(current_px * 0.995, 2) if not is_buy else round(current_px * 1.005, 2)
        
        print(f"\nClosing position at ~${current_px:.2f}...")
        result = exchange.order(
            'SOL',
            is_buy,
            abs(size),
            limit_px,
            {"limit": {"tif": "Gtc"}},
            True  # reduce_only
        )
        
        print(f"Close result: {result}")

print("\n[OK] Position closure complete")
