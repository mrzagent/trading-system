#!/usr/bin/env python3
"""Place SOL, BTC, ETH trades on agent wallet"""
import os
import sys
sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

# FORCE CORRECT AGENT WALLET KEY
os.environ['HYPERLIQUID_PRIVATE_KEY'] = '0x5dc4eea052a2eac43ce453bbb116ae6c9f8a87daf3ccb455064cb9d0dbe62906'
os.environ['HYPERLIQUID_WALLET'] = '0x89823A4f85cc8ef3A5574E8a56741A7b4562f288'

from eth_account import Account
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange

# Agent wallet
PRIVATE_KEY = os.environ['HYPERLIQUID_PRIVATE_KEY']
account = Account.from_key(PRIVATE_KEY)
WALLET = account.address

BASE_URL = "https://api.hyperliquid-testnet.xyz"

info = Info(base_url=BASE_URL)
exchange = Exchange(wallet=account, base_url=BASE_URL)

print("=" * 60)
print("OPENING TRADES ON AGENT WALLET")
print("=" * 60)
print(f"Wallet: {WALLET}")

# Check balance
state = info.user_state(WALLET)
account_value = float(state.get('marginSummary', {}).get('accountValue', 0))
print(f"Account Value: ${account_value:.2f}")

if account_value < 50:
    print("ERROR: Insufficient balance for trades")
    sys.exit(1)

# Get prices
mids = info.all_mids()

# Trade config: (coin, margin, leverage)
trades = [
    ("BTC", 40, 3),   # $40 margin, 3x = $120 notional
    ("ETH", 40, 3),   # $40 margin, 3x = $120 notional  
    ("SOL", 30, 3),   # $30 margin, 3x = $90 notional
]

print("\n" + "=" * 60)

for coin, margin, leverage in trades:
    price = float(mids.get(coin, 0))
    if price == 0:
        print(f"[ERROR] Could not get {coin} price")
        continue
    
    notional = margin * leverage
    sz = notional / price
    sz_rounded = round(sz, 5) if coin == "BTC" else round(sz, 4)
    
    print(f"\n{coin}:")
    print(f"  Price: ${price:,.2f}")
    print(f"  Margin: ${margin}")
    print(f"  Leverage: {leverage}x")
    print(f"  Notional: ${notional}")
    print(f"  Size: {sz_rounded} {coin}")
    print(f"  Placing LONG order...")
    
    result = exchange.market_open(
        name=coin,
        is_buy=True,
        sz=sz_rounded
    )
    
    if result.get('status') == 'ok':
        statuses = result.get('response', {}).get('data', {}).get('statuses', [])
        if statuses and 'filled' in statuses[0]:
            fill = statuses[0]['filled']
            print(f"  [OK] Filled! {fill.get('totalSz')} @ ${fill.get('avgPx')}")
        elif statuses and 'error' in statuses[0]:
            print(f"  [ERROR] {statuses[0]['error']}")
        else:
            print(f"  Result: {result}")
    else:
        print(f"  [ERROR] {result}")

print("\n" + "=" * 60)
print("All orders submitted!")
print("=" * 60)

# Show final positions
state = info.user_state(WALLET)
positions = state.get('assetPositions', [])
print(f"\nFinal Positions: {len(positions)}")
for pos in positions:
    p = pos.get('position', {})
    c = p.get('coin')
    s = p.get('szi')
    e = p.get('entryPx')
    print(f"  {c}: {s} @ ${e}")
