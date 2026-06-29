#!/usr/bin/env python3
"""Verify signature and recover address"""
import sys
sys.path.insert(0, r'D:\dev\trading')

from eth_account import Account
from eth_account.messages import encode_defunct
import json

# The signature from the debug output
signature_hex = "0x8efeb59020fbc47806527b0c14a7e730741b2afeee1466e79212127d753c09d442d90a5c51bb129cc1f206694c2d02bc1d4263d5fe2224c18950ee86000971f71b"

# The message that was signed
action = {
    "type": "order",
    "orders": [{"a": 3, "b": True, "p": "67521", "s": "0.0001", "r": False, "t": {"limit": {"tif": "Ioc"}}}],
    "grouping": "na"
}
message_str = json.dumps(action, separators=(',', ':'))
message = encode_defunct(text=message_str)

print(f"Message: {message_str}")
print(f"Signature: {signature_hex}")

# Recover the address from the signature
from eth_account._utils.signing import to_standard_signature_bytes
from eth_account._utils.legacy_transactions import ALLOWED_LIST

# Try to recover
from eth_keys import keys
sig_bytes = bytes.fromhex(signature_hex[2:])
r = sig_bytes[:32]
s = sig_bytes[32:64]
v = sig_bytes[64]
if v == 27:
    v = 0
elif v == 28:
    v = 1
else:
    v = v

signature_obj = keys.Signature(vrs=(v, int.from_bytes(r, 'big'), int.from_bytes(s, 'big')))
msg_hash = message.body
recovered_pubkey = signature_obj.recover_public_key_from_msg_hash(msg_hash)
recovered_address = recovered_pubkey.to_checksum_address()

print(f"\nRecovered address: {recovered_address}")

# Compare with expected
AGENT = '0x89823A4f85cc8ef3A5574E8a56741A7b4562f288'
MAIN = '0x97c465489243175580fcDe624c2ef640c1897a00'

print(f"\nExpected agent: {AGENT}")
print(f"Expected main: {MAIN}")
print(f"Match agent: {recovered_address.lower() == AGENT.lower()}")
print(f"Match main: {recovered_address.lower() == MAIN.lower()}")
