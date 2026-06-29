#!/usr/bin/env python3
"""Debug script to inspect full state object from Hyperliquid API"""
import sys
import json

sys.path.insert(0, r'D:\dev\trading')

from hyperliquid.info import Info

MAIN_WALLET = '0x97c465489243175580fcDe624c2ef640c1897a00'
BASE_URL = "https://api.hyperliquid-testnet.xyz"

info = Info(base_url=BASE_URL)
state = info.user_state(MAIN_WALLET)

print("=== FULL STATE OBJECT ===")
print(json.dumps(state, indent=2))

print("\n=== marginSummary fields ===")
ms = state.get('marginSummary', {})
for k, v in ms.items():
    print(f"  {k}: {v}")

print("\n=== crossMarginSummary fields ===")
cms = state.get('crossMarginSummary', {})
for k, v in cms.items():
    print(f"  {k}: {v}")

print("\n=== Top-level keys ===")
for k in state.keys():
    val = state[k]
    if not isinstance(val, (list, dict)):
        print(f"  {k}: {val}")
    else:
        print(f"  {k}: (type={type(val).__name__}, len={len(val)})")
