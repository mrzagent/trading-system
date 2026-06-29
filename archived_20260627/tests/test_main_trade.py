"""Test if MAIN wallet can trade directly"""
import os
import sys
sys.path.insert(0, r'D:\dev\trading')

from dotenv import load_dotenv
load_dotenv(os.path.expanduser('~/.openclaw/.env'))

from trade_executor import TradeExecutor, RiskConfig

print("Testing trade with MAIN wallet context...")

executor = TradeExecutor(RiskConfig())

# Check balance via portfolio
balance = executor.client.get_balance()
print(f"Balance: ${balance:.2f}")

# The issue is we don't have MAIN wallet's private key
# We only have AGENT wallet's private key

print("\nWe need MAIN wallet's private key to trade directly.")
print("Or we need to properly authorize AGENT wallet.")
print("\nAgent wallet:", os.getenv('HYPERLIQUID_WALLET'))
print("Main wallet: 0x97c465489243175580fcDe624c2ef640c1897a00")
