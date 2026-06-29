"""Test SDK without full initialization"""
import os
from dotenv import load_dotenv
load_dotenv(os.path.expanduser('~/.openclaw/.env'))

from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils.signing import OrderType

print("Loading wallet...")
private_key = os.getenv('HYPERLIQUID_PRIVATE_KEY')
wallet = Account.from_key(private_key)
print(f"Wallet: {wallet.address}")

print("\nConnecting to Info API...")
info = Info(base_url='https://api.hyperliquid-testnet.xyz', skip_ws=True)
print("Info connected")

print("\nFetching meta...")
meta = info.meta()
print(f"Meta: {len(meta.get('universe', []))} assets")

print("\nChecking balance...")
main_wallet = '0x97c465489243175580fcde624c2ef640c1897a00'
state = info.user_state(main_wallet)
balance = float(state.get('marginSummary', {}).get('accountValue', 0))
print(f"Balance: ${balance:.2f}")

print("\nInitializing Exchange...")
exchange = Exchange(
    wallet=wallet,
    base_url='https://api.hyperliquid-testnet.xyz',
    account_address=main_wallet,
    meta=meta  # Pass meta to avoid re-fetching
)
print("Exchange initialized")

print("\nPlacing order...")
order_type: OrderType = {"limit": {"tif": "Ioc"}}
result = exchange.order(
    name='SOL',
    is_buy=True,
    sz=1.0,
    limit_px=80.0,  # High slippage for market-like
    order_type=order_type,
    reduce_only=False
)
print(f"Result: {result}")
