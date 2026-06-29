"""Verify the trade was placed on HyperLiquid"""
from trade_executor import TradeExecutor, RiskConfig
import requests
from datetime import datetime, timedelta

executor = TradeExecutor(RiskConfig())

print("Verifying trade on HyperLiquid...")
print(f"Main wallet: {executor.client.MAIN_WALLET}")

# Check positions
positions = executor.client.get_positions()
print(f"\nPositions: {len(positions)}")
total_sol = 0
for p in positions:
    if p.get('coin') == 'SOL':
        size = float(p.get('szi', 0))
        total_sol += size
        print(f"  SOL: {size} @ ${p.get('entryPx', 'unknown')}")

print(f"\nTotal SOL position: {total_sol}")

# Check recent fills
print("\nRecent fills (last 5 minutes):")
try:
    response = requests.post(
        'https://api.hyperliquid-testnet.xyz/info',
        json={
            'type': 'userFills',
            'user': executor.client.MAIN_WALLET,
            'startTime': int((datetime.now() - timedelta(minutes=5)).timestamp() * 1000)
        },
        timeout=10
    )
    fills = response.json()
    for fill in fills:
        print(f"  {fill.get('coin')} {fill.get('side')} {fill.get('sz')} @ ${fill.get('px')}")
except Exception as e:
    print(f"Error: {e}")
