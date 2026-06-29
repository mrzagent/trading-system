"""Test API with detailed error capture"""
import requests
import json
import time
from eth_account import Account
from eth_account.messages import encode_defunct
import os
from dotenv import load_dotenv
load_dotenv(os.path.expanduser('~/.openclaw/.env'))

# Build the exact payload
private_key = os.getenv('HYPERLIQUID_PRIVATE_KEY')
account = Account.from_key(private_key)

action = {
    "type": "order",
    "orders": [{
        "coin": "SOL",
        "is_buy": True,
        "sz": "1.0",
        "limit_px": "73.0",
        "order_type": "Market",
        "reduce_only": False
    }],
    "grouping": "na",
    "builder": None
}

nonce = int(time.time() * 1000)
message_str = json.dumps(action, separators=(',', ':'), sort_keys=True) + str(nonce)
message = encode_defunct(text=message_str)
signed = account.sign_message(message)
signature = signed.signature.hex()

payload = {
    "action": action,
    "nonce": nonce,
    "signature": signature
}

print("Request payload:")
print(json.dumps(payload, indent=2))

print("\n\nSending request...")
response = requests.post(
    'https://api.hyperliquid-testnet.xyz/exchange',
    json=payload
)

print(f"\nStatus: {response.status_code}")
print(f"Response headers: {dict(response.headers)}")
print(f"Response body: {response.text}")
