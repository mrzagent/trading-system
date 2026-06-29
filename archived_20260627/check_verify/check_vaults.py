"""Check if MAIN wallet has vaults"""
import requests
import json

MAIN = '0x97c465489243175580fcDe624c2ef640c1897a00'

print("Checking vaults for MAIN wallet...")

# Try to get vault info
try:
    response = requests.post(
        'https://api.hyperliquid-testnet.xyz/info',
        json={"type": "vaults", "user": MAIN},
        timeout=10
    )
    print(f"Vaults: {response.json()}")
except Exception as e:
    print(f"Error: {e}")

# Try user vaults
try:
    response = requests.post(
        'https://api.hyperliquid-testnet.xyz/info',
        json={"type": "userVaults", "user": MAIN},
        timeout=10
    )
    print(f"User Vaults: {response.json()}")
except Exception as e:
    print(f"Error: {e}")
