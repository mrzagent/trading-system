#!/usr/bin/env python3
"""Transfer USDC from main wallet to agent wallet on Hyperliquid testnet"""
import os
import sys
sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

from dotenv import load_dotenv
from eth_account import Account

load_dotenv(r'C:\Users\mrztms\.openclaw\.env')

# Wallet with funds (derived from private key)
MAIN_KEY = os.getenv('HYPERLIQUID_PRIVATE_KEY')
account = Account.from_key(MAIN_KEY)
MAIN_WALLET = account.address  # This will be 0x91D5...6aee

# Destination wallet (agent)
AGENT_WALLET = "0x89823A4f85cc8ef3A5574E8a56741A7b4562f288"
TRANSFER_AMOUNT = 100  # USDC

from hyperliquid.info import Info
from hyperliquid.exchange import Exchange

BASE_URL = "https://api.hyperliquid-testnet.xyz"

print("=" * 60)
print("HYPERLIQUID USDC TRANSFER")
print("=" * 60)
print(f"\nFrom: {MAIN_WALLET}")
print(f"To:   {AGENT_WALLET}")
print(f"Amount: {TRANSFER_AMOUNT} USDC")
print()

# Create exchange client
exchange = Exchange(wallet=account, base_url=BASE_URL)
info = Info(base_url=BASE_URL)

# Check balance before
print("[+] Checking source wallet balance...")
# Use open_orders or user_state endpoint
user_state = info.user_state(MAIN_WALLET)
account_value = float(user_state.get('marginSummary', {}).get('accountValue', 0))
withdrawable = float(user_state.get('withdrawable', 0))

print(f"    Account Value: ${account_value:.2f}")
print(f"    Withdrawable:  ${withdrawable:.2f}")

if withdrawable < TRANSFER_AMOUNT:
    print(f"\n[ERROR] Insufficient withdrawable balance!")
    print(f"        Need: ${TRANSFER_AMOUNT}")
    print(f"        Have: ${withdrawable:.2f}")
    sys.exit(1)

# Use the SDK's withdraw method
print(f"\n[+] Submitting transfer...")
try:
    result = exchange.withdraw(
        destination=AGENT_WALLET,
        amount=TRANSFER_AMOUNT
    )
    
    print("[OK] Transfer submitted successfully!")
    print(f"     Response: {result}")
        
except Exception as e:
    print(f"[ERROR] Transfer failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("Transfer complete!")
print("=" * 60)
