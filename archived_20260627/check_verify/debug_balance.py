#!/usr/bin/env python3
"""Debug Hyperliquid testnet balance"""
import os
import sys
import json

sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

from trade_executor import HyperliquidClient
from dotenv import load_dotenv

load_dotenv(r'C:\Users\mrztms\.openclaw\.env')

wallet = os.getenv('HYPERLIQUID_WALLET')
print(f"Wallet: {wallet}")
print()

client = HyperliquidClient(wallet_address=wallet)

print("=" * 60)
print("RAW API RESPONSE")
print("=" * 60)
response = client.get_user_state()
print(json.dumps(response, indent=2))

print("\n" + "=" * 60)
print("SPOT BALANCE CHECK")
print("=" * 60)
try:
    spot_response = client._post('/info', {
        "type": "spotClearinghouseState",
        "user": wallet
    })
    print(json.dumps(spot_response, indent=2))
except Exception as e:
    print(f"Spot check failed: {e}")

print("\n" + "=" * 60)
print("TOKEN BALANCES")
print("=" * 60)
try:
    token_response = client._post('/info', {
        "type": "tokenBalances",
        "user": wallet
    })
    print(json.dumps(token_response, indent=2))
except Exception as e:
    print(f"Token balances failed: {e}")
