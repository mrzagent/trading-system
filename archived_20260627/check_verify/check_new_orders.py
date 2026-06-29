"""Check for new orders"""
from trade_executor import TradeExecutor, RiskConfig
from datetime import datetime, timedelta

executor = TradeExecutor(RiskConfig())

print("Checking for recent orders...")

# Check fills from last 10 minutes
try:
    import requests
    response = requests.post(
        'https://api.hyperliquid-testnet.xyz/info',
        json={
            "type": "userFills",
            "user": executor.client.MAIN_WALLET,
            "startTime": int((datetime.now() - timedelta(minutes=10)).timestamp() * 1000)
        },
        timeout=10
    )
    fills = response.json()
    print(f"Recent fills: {len(fills)}")
    for fill in fills[-3:]:
        print(f"  {fill.get('coin')} {fill.get('side')} {fill.get('sz')} @ ${fill.get('px')} (oid: {fill.get('oid')})")
        print(f"    Time: {datetime.fromtimestamp(fill.get('time')/1000).strftime('%H:%M:%S')}")
except Exception as e:
    print(f"Error: {e}")

# Check positions
print("\nCurrent positions:")
positions = executor.client.get_positions()
for p in positions:
    print(f"  {p.get('coin')}: {p.get('szi', p.get('size', 'unknown'))} @ ${p.get('entryPx', 'unknown')}")
