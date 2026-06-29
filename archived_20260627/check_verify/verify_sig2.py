#!/usr/bin/env python3
"""Verify signature using eth_account directly"""
import sys
sys.path.insert(0, r'D:\dev\trading')

from eth_account import Account
from eth_account.messages import encode_defunct
import json

# The expected wallets
AGENT_KEY = '0x5dc4eea052a2eac43ce453bbb116ae6c9f8a87daf3ccb455064cb9d0dbe62906'
MAIN_KEY = '0x8c91e5e717c5f5196d9e4b658c374bdc18077c295e5728a1accf7ecebedbfe55'

agent_account = Account.from_key(AGENT_KEY)
main_account = Account.from_key(MAIN_KEY)

print(f"Agent address: {agent_account.address}")
print(f"Main address: {main_account.address}")

# The message that was signed
action = {
    "type": "order",
    "orders": [{"a": 3, "b": True, "p": "67521", "s": "0.0001", "r": False, "t": {"limit": {"tif": "Ioc"}}}],
    "grouping": "na"
}
message_str = json.dumps(action, separators=(',', ':'))
message = encode_defunct(text=message_str)

print(f"\nMessage: {message_str}")

# Sign with agent key and compare
agent_signed = agent_account.sign_message(message)
print(f"\nAgent signature: {agent_signed.signature.hex()}")

# Sign with main key and compare
main_signed = main_account.sign_message(message)
print(f"Main signature: {main_signed.signature.hex()}")

# The signature from debug output
observed_sig = "0x8efeb59020fbc47806527b0c14a7e730741b2afeee1466e79212127d753c09d442d90a5c51bb129cc1f206694c2d02bc1d4263d5fe2224c18950ee86000971f71b"
print(f"\nObserved sig: {observed_sig}")

# Check which one matches
if agent_signed.signature.hex().lower() == observed_sig.lower():
    print("\n[OK] Signature matches AGENT key!")
elif main_signed.signature.hex().lower() == observed_sig.lower():
    print("\n[FAIL] Signature matches MAIN key!")
else:
    print("\n[?] Signature doesn't match either (different nonce/message?)")
