"""Check open orders"""
from trade_executor import TradeExecutor, RiskConfig
import requests

executor = TradeExecutor(RiskConfig())

# Check open orders
response = requests.post(
    'https://api.hyperliquid-testnet.xyz/info',
    json={'type': 'openOrders', 'user': executor.client.MAIN_WALLET},
    timeout=10
)
orders = response.json()
print(f'Open orders: {len(orders)}')
for o in orders:
    print(f"  {o['coin']} {o['side']} {o['sz']} @ ${o['limitPx']} (oid: {o.get('oid')})")
