"""Test using official HyperLiquid SDK"""
import os
from dotenv import load_dotenv
load_dotenv(os.path.expanduser('~/.openclaw/.env'))

from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info

# Create wallet from private key
private_key = os.getenv('HYPERLIQUID_PRIVATE_KEY')
wallet = Account.from_key(private_key)

print(f'Agent wallet: {wallet.address}')

# Connect to testnet
exchange = Exchange(
    wallet=wallet,
    base_url='https://api.hyperliquid-testnet.xyz'
)

info = Info(base_url='https://api.hyperliquid-testnet.xyz')

# Check MAIN wallet balance
main_wallet = '0x97c465489243175580fcDe624c2ef640c1897a00'
main_state = info.user_state(main_wallet)
main_balance = float(main_state.get('marginSummary', {}).get('accountValue', 0))
print(f'MAIN Wallet Balance: ${main_balance:.2f}')

# Try to place a small order on behalf of MAIN
try:
    print(f'\nPlacing order for MAIN wallet...')
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
