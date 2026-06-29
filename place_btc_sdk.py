#!/usr/bin/env python3
"""Place BTC LONG trade using official Hyperliquid SDK"""
import os
import sys
sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

from dotenv import load_dotenv
from eth_account import Account

load_dotenv(r'C:\Users\mrztms\.openclaw\.env')

# Wallet credentials
PRIVATE_KEY = os.getenv('HYPERLIQUID_PRIVATE_KEY')
account = Account.from_key(PRIVATE_KEY)
WALLET = account.address

print("=" * 60)
print("HYPERLIQUID BTC TRADE")
print("=" * 60)
print(f"Wallet: {WALLET}")

from hyperliquid.info import Info
from hyperliquid.exchange import Exchange

BASE_URL = "https://api.hyperliquid-testnet.xyz"

info = Info(base_url=BASE_URL)
exchange = Exchange(wallet=account, base_url=BASE_URL)

# Get current BTC price
mids = info.all_mids()
btc_price = float(mids.get('BTC', 0))
print(f"BTC Price: ${btc_price:,.2f}")

# Trade parameters - use larger size
margin = 50.0       # $50 margin
leverage = 3.0      # 3x leverage
notional = margin * leverage  # $150 notional
sz = notional / btc_price

print(f"\nTrade Details:")
print(f"  Size: {sz:.6f} BTC")
print(f"  Notional: ${notional:.2f}")
print(f"  Leverage: {leverage:.0f}x")
print(f"  Margin: ${margin:.2f}")

# Check balance
user_state = info.user_state(WALLET)
account_value = float(user_state.get('marginSummary', {}).get('accountValue', 0))
print(f"\nAccount Value: ${account_value:.2f}")

if account_value < margin:
    print("ERROR: Insufficient balance")
    sys.exit(1)

# Place market order - use rounding to 4 decimals
sz_rounded = round(sz, 4)
print(f"\nPlacing MARKET BUY order for {sz_rounded} BTC...")
result = exchange.market_open(
    name="BTC",
    is_buy=True,
    sz=sz_rounded
)

print(f"\nResult: {result}")

if result.get('status') == 'ok':
    statuses = result.get('response', {}).get('data', {}).get('statuses', [])
    if statuses and 'error' in statuses[0]:
        print(f"[ERROR] {statuses[0]['error']}")
    else:
        print("[OK] Order placed successfully!")
else:
    print(f"[ERROR] {result}")
