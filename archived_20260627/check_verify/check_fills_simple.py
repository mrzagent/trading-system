"""Check fills on MAIN wallet"""
import requests
import json
from datetime import datetime, timedelta

MAIN = '0x97c465489243175580fcDe624c2ef640c1897a00'

print("Checking fills for MAIN wallet...")

# Get fills from last 48 hours
try:
    response = requests.post(
        'https://api.hyperliquid-testnet.xyz/info',
        json={
            "type": "userFills", 
            "user": MAIN,
            "startTime": int((datetime.now() - timedelta(days=2)).timestamp() * 1000)
        },
        timeout=10
    )
    fills = response.json()
    print(f"Found {len(fills)} fills")
    
    for fill in fills[-5:]:  # Last 5 fills
        print(f"\n  {fill.get('coin')} {fill.get('side')} {fill.get('sz')} @ ${fill.get('px')}")
        print(f"  Time: {datetime.fromtimestamp(fill.get('time')/1000)}")
        print(f"  Hash: {fill.get('hash')}")
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
