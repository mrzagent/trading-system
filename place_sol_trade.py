#!/usr/bin/env python3
"""Place a SOL LONG trade on Hyperliquid testnet"""
import os
import sys
sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

from trade_executor import TradeExecutor
from dotenv import load_dotenv

load_dotenv(r'C:\Users\mrztms\.openclaw\.env')

# Create executor
executor = TradeExecutor()

# Get current SOL price
sol_price = executor.client.get_mid_price('SOL')
print(f"Current SOL price: ${sol_price:,.2f}")

# Trade parameters
notional = 10.0  # $10
leverage = 10.0  # 10x
margin = notional / leverage  # $1 margin required

# Size in SOL coins
sz = notional / sol_price
print(f"Position size: {sz:.6f} SOL")
print(f"Notional value: ${notional:.2f}")
print(f"Leverage: {leverage:.0f}x")
print(f"Margin required: ${margin:.2f}")
print()

# Place the order
print("Placing order...")
result = executor.open_position_real(
    symbol='SOL',
    side='long',
    sz=sz,
    order_type='Market'
)
print(f"Result: {result}")
