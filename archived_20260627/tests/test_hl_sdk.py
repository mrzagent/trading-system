"""Test using official HyperLiquid SDK"""
import os
from dotenv import load_dotenv
load_dotenv(os.path.expanduser('~/.openclaw/.env'))

from hyperliquid.exchange import Exchange
from hyperliquid.info import Info

# Connect to testnet
exchange = Exchange(
    wallet_address=os.getenv('HYPERLIQUID_WALLET'),
    private_key=os.getenv('HYPERLIQUID_PRIVATE_KEY'),
    base_url='https://api.hyperliquid-testnet.xyz'
)

info = Info(base_url='https://api.hyperliquid-testnet.xyz')

# Check balance
wallet = os.getenv('HYPERLIQUID_WALLET')
state = info.user_state(wallet)
balance = float(state.get('marginSummary', {}).get('accountValue', 0))
print(f'AGENT Wallet Balance: ${balance:.2f}')

# Check if vault is set
main_wallet = '0x97c465489243175580fcDe624c2ef640c1897a00'
print(f'\nTrying to place order on behalf of MAIN: {main_wallet}')

# Try to place a small order
try:
    result = exchange.order(
        coin='SOL',
        is_buy=True,
        sz=1.0,
        limit_px=73.0,
        order_type='Market',
        vault_address=main_wallet  # Trade on behalf of main wallet
    )
    print(f'Order result: {result}')
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
