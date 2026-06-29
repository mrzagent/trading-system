#!/usr/bin/env python3
"""Debug script to check spot balances and all available endpoints"""
import sys
import json

sys.path.insert(0, r'D:\dev\trading')

from hyperliquid.info import Info

MAIN_WALLET = '0x97c465489243175580fcDe624c2ef640c1897a00'
BASE_URL = "https://api.hyperliquid-testnet.xyz"

info = Info(base_url=BASE_URL)

print("=== SPOT CLEARINGHOUSE STATE ===")
try:
    spot_state = info.spot_clearinghouse_state(MAIN_WALLET)
    print(json.dumps(spot_state, indent=2))
except Exception as e:
    print(f"Error: {e}")

print("\n=== USER PORTFOLIO / META ===")
try:
    # Try fetching portfolio or any other useful endpoint
    portfolio = info.post("/info", {"type": "portfolio", "user": MAIN_WALLET})
    print(json.dumps(portfolio, indent=2))
except Exception as e:
    print(f"portfolio error: {e}")

print("\n=== SPOT META AND ASSET CTXS ===")
try:
    spot_meta = info.spot_meta_and_asset_ctxs()
    # just print the token names
    tokens = spot_meta[0].get('tokens', [])
    print(f"Number of spot tokens: {len(tokens)}")
    for t in tokens[:10]:
        print(f"  {t.get('name')}: index={t.get('index')}")
except Exception as e:
    print(f"Error: {e}")
