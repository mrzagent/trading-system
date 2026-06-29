#!/usr/bin/env python3
"""Place SOL trade on agent wallet"""
import os
import sys
sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

# FORCE CORRECT AGENT WALLET KEY
os.environ['HYPERLIQUID_PRIVATE_KEY'] = '0x5dc4eea052a2eac43ce453bbb116ae6c9f8a87daf3ccb455064cb9d0dbe62906'

from eth_account import Account
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange

account = Account.from_key(os.environ['HYPERLIQUID_PRIVATE_KEY'])
BASE_URL = "https://api.hyperliquid-testnet.xyz"

info = Info(base_url=BASE_URL)
exchange = Exchange(wallet=account, base_url=BASE_URL)

print("Placing SOL trade...")

mids = info.all_mids()
price = float(mids.get('SOL', 0))
print(f"SOL Price: ${price}")

# Try smaller size with 2 decimals
notional = 90  # $90 at 3x = $30 margin
sz = round(notional / price, 2)
print(f"Size: {sz} SOL")

result = exchange.market_open(name='SOL', is_buy=True, sz=sz)
print(f"Result: {result}")
