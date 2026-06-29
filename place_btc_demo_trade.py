#!/usr/bin/env python3
"""Place a BTC demo trade on Hyperliquid testnet - $20 at 3x leverage"""
import os
import sys
sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

from trade_executor import TradeExecutor
from dotenv import load_dotenv

load_dotenv(r'C:\Users\mrztms\.openclaw\.env')

# Create executor
executor = TradeExecutor()

# Get current BTC price
btc_price = executor.client.get_mid_price('BTC')
print(f"Current BTC price: ${btc_price:,.2f}")

# Trade parameters
margin = 20.0       # $20 margin
leverage = 3.0      # 3x leverage
notional = margin * leverage  # $60 notional value

# Size in BTC coins
sz = notional / btc_price
print(f"\nPosition size: {sz:.6f} BTC")
print(f"Notional value: ${notional:.2f}")
print(f"Leverage: {leverage:.0f}x")
print(f"Margin required: ${margin:.2f}")
print()

# Confirm before placing
input("Press Enter to confirm trade...")

# Place the order
print("Placing order...")
result = executor.open_position_real(
    symbol='BTC',
    side='long',
    sz=sz,
    order_type='Market'
)
print(f"\nResult: {result}")
