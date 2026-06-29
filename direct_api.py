#!/usr/bin/env python3
"""Direct HTTP request to testnet API"""
import requests
import json

url = "https://api.hyperliquid-testnet.xyz/info"
headers = {"Content-Type": "application/json"}

# Query agent wallet
payload = {
    "type": "userState",
    "user": "0x89823A4f85cc8ef3A5574E8a56741A7b4562f288"
}

print(f'Requesting: {url}')
print(f'Payload: {json.dumps(payload)}')
print()

response = requests.post(url, headers=headers, json=payload)
print(f'Status: {response.status_code}')
print(f'Headers: {dict(response.headers)}')
print(f'Raw text: {response.text[:500]}')
