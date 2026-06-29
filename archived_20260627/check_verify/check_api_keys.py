"""Check API key authorization on HyperLiquid"""
import requests
import json

MAIN = '0x97c465489243175580fcDe624c2ef640c1897a00'
AGENT = '0x89823A4f85cc8ef3A5574E8a56741A7b4562f288'

print("Checking API key authorization...")
print(f"Main: {MAIN}")
print(f"Agent: {AGENT}")

# Try to get API key info
try:
    response = requests.post(
        'https://api.hyperliquid-testnet.xyz/info',
        json={"type": "apiKey", "user": MAIN},
        timeout=10
    )
    print(f"\nAPI keys for MAIN: {response.json()}")
except Exception as e:
    print(f"Error: {e}")

# Try to see if agent can access main's data
try:
    response = requests.post(
        'https://api.hyperliquid-testnet.xyz/info',
        json={"type": "clearinghouseState", "user": MAIN},
        timeout=10
    )
    data = response.json()
    print(f"\nMain clearinghouseState: {json.dumps(data, indent=2)[:500]}")
except Exception as e:
    print(f"Error: {e}")
