#!/usr/bin/env python3
"""Debug Exchange wallet configuration"""
import os
import sys

# Force agent wallet env
os.environ['HYPERLIQUID_WALLET'] = '0x89823A4f85cc8ef3A5574E8a56741A7b4562f288'
os.environ['HYPERLIQUID_PRIVATE_KEY'] = '0x5dc4eea052a2eac43ce453bbb116ae6c9f8a87daf3ccb455064cb9d0dbe62906'

sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info

# Create account from agent private key
account = Account.from_key(os.environ['HYPERLIQUID_PRIVATE_KEY'])
AGENT_ADDRESS = account.address

print("=" * 60)
print("DEBUGGING EXCHANGE WALLET CONFIGURATION")
print("=" * 60)
print(f"Environment HYPERLIQUID_WALLET: {os.environ.get('HYPERLIQUID_WALLET')}")
print(f"Account address from key: {AGENT_ADDRESS}")
print(f"Match: {AGENT_ADDRESS.lower() == os.environ.get('HYPERLIQUID_WALLET', '').lower()}")
print()

# Create Exchange
BASE_URL = "https://api.hyperliquid-testnet.xyz"
exchange = Exchange(wallet=account, base_url=BASE_URL)

# Check what wallet the exchange is using
print(f"Exchange wallet attribute: {getattr(exchange, 'wallet', 'N/A')}")
print(f"Exchange base_url: {getattr(exchange, 'base_url', 'N/A')}")

# Try to access the wallet address from the exchange
if hasattr(exchange, 'wallet'):
    if hasattr(exchange.wallet, 'address'):
        print(f"Exchange.wallet.address: {exchange.wallet.address}")

# Check Info class too
info = Info(base_url=BASE_URL)
print(f"\nInfo base_url: {getattr(info, 'base_url', 'N/A')}")

# Now let's check if the Exchange is signing with the correct key
print("\n" + "=" * 60)
print("TEST: Place a tiny ETH trade and check which wallet it lands on")
print("=" * 60)

# Get ETH price
mids = info.all_mids()
eth_price = float(mids.get('ETH', 0))
sz = round(5 / eth_price, 4)  # $5 worth

print(f"ETH Price: ${eth_price:,.2f}")
print(f"Size: {sz} ETH")
print()

# Place order
result = exchange.market_open(name='ETH', is_buy=True, sz=sz)
print(f"Order result: {result}")

# Get the OID from result
if result.get('status') == 'ok':
    oid = result['response']['data']['statuses'][0].get('filled', {}).get('oid', 'N/A')
    print(f"OID: {oid}")
    print()
    print("Checking which wallet this OID appears on...")
    
    # Check both wallets
    MAIN_WALLET = '0x97c465489243175580fcDe624c2ef640c1897a00'
    
    main_fills = info.user_fills(MAIN_WALLET)
    agent_fills = info.user_fills(AGENT_ADDRESS)
    
    main_oids = [f.get('oid') for f in main_fills]
    agent_oids = [f.get('oid') for f in agent_fills]
    
    print(f"Main wallet has OID {oid}: {oid in main_oids}")
    print(f"Agent wallet has OID {oid}: {oid in agent_oids}")
