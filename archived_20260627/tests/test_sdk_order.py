"""Test using official HyperLiquid SDK with agent wallet"""
import os
import sys
sys.path.insert(0, r'D:\dev\trading')

from dotenv import load_dotenv
load_dotenv(os.path.expanduser('~/.openclaw/.env'))

from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info

# Agent wallet for signing
private_key = os.getenv('HYPERLIQUID_PRIVATE_KEY')
agent_wallet = Account.from_key(private_key)

print(f'Agent wallet: {agent_wallet.address}')

# Connect to testnet using agent wallet for signing
# But specify MAIN wallet as the account to trade for
main_wallet = '0x97c465489243175580fcDe624c2ef640c1897a00'

exchange = Exchange(
    wallet=agent_wallet,
    base_url='https://api.hyperliquid-testnet.xyz',
    account_address=main_wallet  # Trade on behalf of main account
)

info = Info(base_url='https://api.hyperliquid-testnet.xyz')

# Check MAIN wallet balance
main_state = info.user_state(main_wallet)
main_balance = float(main_state.get('marginSummary', {}).get('accountValue', 0))
print(f'MAIN Wallet Balance: ${main_balance:.2f}')

# Check positions on MAIN wallet
main_positions = info.user_state(main_wallet).get('assetPositions', [])
print(f'MAIN Positions: {len(main_positions)}')

# Try to place order
print(f'\nPlacing order for MAIN wallet...')
try:
    result = exchange.order(
        coin='SOL',
        is_buy=True,
        sz=1.0,
        limit_px=73.0,
        order_type='Market'
    )
    print(f'Order result: {result}')
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
