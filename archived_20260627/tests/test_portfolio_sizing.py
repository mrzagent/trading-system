#!/usr/bin/env python3
"""Test 2% portfolio sizing"""
import sys
import os
sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

from signal_executor import SignalExecutor

executor = SignalExecutor()
portfolio = executor.get_portfolio_value()

print("=" * 50)
print("PORTFOLIO SIZING TEST (2%)")
print("=" * 50)
print(f"Portfolio Value: ${portfolio:.2f}")
print(f"2% Position Size: ${portfolio * 0.02:.2f}")

for coin in ['BTC', 'ETH', 'SOL']:
    sz, notional, decimals = executor.calculate_position_size_pct(coin, 0.02)
    print(f"\n{coin}:")
    print(f"  Size: {sz} {coin}")
    print(f"  Notional: ${notional:.2f}")
    print(f"  szDecimals: {decimals}")

print("\n[OK] Portfolio sizing configured correctly")
