"""Check perps account balance"""
import requests
import json

MAIN = '0x97c465489243175580fcDe624c2ef640c1897a00'

print("Checking perps account...")

# Try perps-specific endpoints
endpoints = [
    {"type": "clearinghouseState", "user": MAIN},
    {"type": "perpClearinghouseState", "user": MAIN},
    {"type": "spotClearinghouseState", "user": MAIN},
]

for endpoint in endpoints:
    try:
        print(f"\nTrying {endpoint['type']}...")
        response = requests.post(
            'https://api.hyperliquid-testnet.xyz/info',
            json=endpoint,
            timeout=10
        )
        data = response.json()
        balance = float(data.get('marginSummary', {}).get('accountValue', 0))
        print(f"  Balance: ${balance:.2f}")
    except Exception as e:
        print(f"  Error: {e}")
