#!/usr/bin/env python3
"""Place $10 ETH trade and track which wallet it lands on"""
import os
import sys
import time

os.environ['HYPERLIQUID_WALLET'] = '0x89823A4f85cc8ef3A5574E8a56741A7b4562f288'
os.environ['HYPERLIQUID_PRIVATE_KEY'] = '0x5dc4eea052a2eac43ce453bbb116ae6c9f8a87daf3ccb455064cb9d0dbe62906'

sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info

account = Account.from_key(os.environ['HYPERLIQUID_PRIVATE_KEY'])
AGENT_ADDRESS = account.address
MAIN_WALLET = '0x97c465489243175580fcDe624c2ef640c1897a00'

print("=" * 60)
print("PLACING $10 ETH TRADE - TRACKING WALLET DESTINATION")
print("=" * 60)
print(f"Agent: {AGENT_ADDRESS}")
print(f"Main:  {MAIN_WALLET}")
print()

BASE_URL = "https://api.hyperliquid-testnet.xyz"
info = Info(base_url=BASE_URL)
exchange = Exchange(wallet=account, base_url=BASE_URL)

# Get ETH price
mids = info.all_mids()
eth_price = float(mids.get('ETH', 0))
sz = round(11 / eth_price, 4)  # $11 to ensure above $10 minimum

print(f"ETH Price: ${eth_price:,.2f}")
print(f"Size: {sz} ETH (~${sz * eth_price:.2f})")
print()

# Place order
print("Placing order...")
result = exchange.market_open(name='ETH', is_buy=True, sz=sz)
print(f"Result: {result}")
print()

if result.get('status') == 'ok':
    status_data = result['response']['data']['statuses'][0]
    if 'filled' in status_data:
        oid = status_data['filled']['oid']
        print(f"[OK] Order filled! OID: {oid}")
        print()
        
        time.sleep(2)
        
        print("Checking fills on both wallets...")
        main_fills = info.user_fills(MAIN_WALLET)
        agent_fills = info.user_fills(AGENT_ADDRESS)
        
        main_oids = [f.get('oid') for f in main_fills]
        agent_oids = [f.get('oid') for f in agent_fills]
        
        print(f"  Main wallet has OID {oid}: {'YES' if oid in main_oids else 'NO'}")
        print(f"  Agent wallet has OID {oid}: {'YES' if oid in agent_oids else 'NO'}")
        
        if oid in main_oids and oid not in agent_oids:
            print("\n[ISSUE] Order landed on MAIN wallet despite using agent key!")
        elif oid in agent_oids and oid not in main_oids:
            print("\n[OK] Order landed on AGENT wallet as expected")
        elif oid in main_oids and oid in agent_oids:
            print("\n[?] Order appears on BOTH wallets (unexpected)")
        else:
            print("\n[?] Order not found on either wallet yet")
    elif 'error' in status_data:
        print(f"[ERROR] Order error: {status_data['error']}")
else:
    print(f"[ERROR] Order failed: {result}")
