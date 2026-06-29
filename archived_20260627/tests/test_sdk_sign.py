"""Test using official SDK signing"""
import os
import sys
sys.path.insert(0, r'D:\dev\trading')

from dotenv import load_dotenv
load_dotenv(os.path.expanduser('~/.openclaw/.env'))

from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils.signing import OrderType

# Agent wallet for signing
private_key = os.getenv('HYPERLIQUID_PRIVATE_KEY')
agent_wallet = Account.from_key(private_key)

print(f'Agent wallet: {agent_wallet.address}')

# Connect to testnet
main_wallet = '0x97c465489243175580fcDe624c2ef640c1897a00'

exchange = Exchange(
    wallet=agent_wallet,
    base_url='https://api.hyperliquid-testnet.xyz',
    account_address=main_wallet
)

info = Info(base_url='https://api.hyperliquid-testnet.xyz')

# Check MAIN wallet balance via SDK
state = info.user_state(main_wallet)
print(f"\nMAIN state keys: {state.keys()}")
if 'marginSummary' in state:
    balance = float(state['marginSummary'].get('accountValue', 0))
    print(f'MAIN Balance: ${balance:.2f}')

# Try to place order using SDK
print(f'\nPlacing order via SDK...')
try:
    result = exchange.order(
        coin='SOL',
        is_buy=True,
        sz=1.0,
        limit_px=73.0,
        order_type=OrderType.MARKET
    )
    print(f'Order result: {result}')
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
