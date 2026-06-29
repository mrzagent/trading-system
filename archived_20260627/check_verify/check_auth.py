"""Check if agent wallet is authorized for main wallet"""
import requests
import json

MAIN = '0x97c465489243175580fcDe624c2ef640c1897a00'
AGENT = '0x89823A4f85cc8ef3A5574E8a56741A7b4562f288'

print("Checking authorization...")
print(f"Main: {MAIN}")
print(f"Agent: {AGENT}")

# Query HyperLiquid for delegations
try:
    response = requests.post(
        'https://api.hyperliquid-testnet.xyz/info',
        json={"type": "delegations", "user": MAIN},
        timeout=10
    )
    print(f"\nDelegations for MAIN:")
    print(response.json())
except Exception as e:
    print(f"Error: {e}")

# Check if agent can query main's state
try:
    response = requests.post(
        'https://api.hyperliquid-testnet.xyz/info',
        json={"type": "clearinghouseState", "user": MAIN},
        timeout=10
    )
    data = response.json()
    balance = float(data.get('marginSummary', {}).get('accountValue', 0))
    print(f"\nMAIN balance: ${balance:.2f}")
except Exception as e:
    print(f"Error: {e}")
