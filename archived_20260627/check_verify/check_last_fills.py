"""Check last fills with dates"""
import requests
import json
from datetime import datetime, timedelta

MAIN = '0x97c465489243175580fcDe624c2ef640c1897a00'

print("Checking all fills for MAIN wallet...")

try:
    response = requests.post(
        'https://api.hyperliquid-testnet.xyz/info',
        json={
            "type": "userFills", 
            "user": MAIN,
            "startTime": int((datetime.now() - timedelta(days=30)).timestamp() * 1000)
        },
        timeout=10
    )
    fills = response.json()
    print(f"Total fills: {len(fills)}")
    
    # Show last 10 fills with dates
    print("\nLast 10 fills:")
    for fill in fills[-10:]:
        time_str = datetime.fromtimestamp(fill.get('time')/1000).strftime('%Y-%m-%d %H:%M')
        print(f"  {time_str}: {fill.get('coin')} {fill.get('side')} {fill.get('sz')} @ ${fill.get('px')}")
        
except Exception as e:
    print(f"Error: {e}")
