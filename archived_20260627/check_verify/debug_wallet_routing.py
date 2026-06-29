#!/usr/bin/env python3
"""
Minimal reproduction script to debug Hyperliquid SDK wallet routing issue.
This script tests if the Exchange class is correctly using the wallet parameter.
"""
import os
import sys

# Clear any existing env vars to ensure clean state
for key in ['HYPERLIQUID_PRIVATE_KEY', 'HYPERLIQUID_WALLET']:
    if key in os.environ:
        del os.environ[key]

# AGENT WALLET - The one we want to use
AGENT_PRIVATE_KEY = '0x5dc4eea052a2eac43ce453bbb116ae6c9f8a87daf3ccb455064cb9d0dbe62906'
AGENT_WALLET = '0x89823A4f85cc8ef3A5574E8a56741A7b4562f288'

# MAIN WALLET - The one trades are incorrectly going to
MAIN_PRIVATE_KEY = '0x8c91e5e717c5f5196d9e4b658c374bdc18077c295e5728a1accf7ecebedbfe55'
MAIN_WALLET = '0x97c465489243175580fcDe624c2ef640c1897a00'

from eth_account import Account
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange

BASE_URL = "https://api.hyperliquid-testnet.xyz"

print("=" * 70)
print("HYPERLIQUID SDK WALLET ROUTING DEBUG")
print("=" * 70)

# Test 1: Create agent wallet account
print("\n--- Test 1: Account Creation ---")
agent_account = Account.from_key(AGENT_PRIVATE_KEY)
print(f"Expected Agent Wallet: {AGENT_WALLET}")
print(f"Actual Account Address: {agent_account.address}")
print(f"Match: {agent_account.address.lower() == AGENT_WALLET.lower()}")

# Test 2: Create Exchange with agent wallet
print("\n--- Test 2: Exchange Class Wallet Assignment ---")
info = Info(base_url=BASE_URL, skip_ws=True)
exchange = Exchange(wallet=agent_account, base_url=BASE_URL)

print(f"Exchange.wallet.address: {exchange.wallet.address}")
print(f"Expected: {AGENT_WALLET}")
print(f"Match: {exchange.wallet.address.lower() == AGENT_WALLET.lower()}")

# Test 3: Check user state for agent wallet
print("\n--- Test 3: Agent Wallet State ---")
try:
    agent_state = info.user_state(AGENT_WALLET)
    agent_balance = float(agent_state.get('marginSummary', {}).get('accountValue', 0))
    print(f"Agent Wallet ({AGENT_WALLET[:10]}...): ${agent_balance:.2f}")
except Exception as e:
    print(f"Error checking agent wallet: {e}")

# Test 4: Check user state for main wallet
print("\n--- Test 4: Main Wallet State ---")
try:
    main_state = info.user_state(MAIN_WALLET)
    main_balance = float(main_state.get('marginSummary', {}).get('accountValue', 0))
    print(f"Main Wallet ({MAIN_WALLET[:10]}...): ${main_balance:.2f}")
except Exception as e:
    print(f"Error checking main wallet: {e}")

# Test 5: Attempt a test order (with very small size that will fail validation)
# This is to see what wallet the order is signed with
print("\n--- Test 5: Order Signing Verification ---")
print("Attempting to place a tiny order to check signing wallet...")

try:
    # Get current BTC price
    mids = info.all_mids()
    btc_price = float(mids.get('BTC', 0))
    print(f"Current BTC price: ${btc_price:,.2f}")
    
    # Try to place a tiny order - this should fail due to size but show us the signing
    result = exchange.market_open(
        name='BTC',
        is_buy=True,
        sz=0.0001  # Very small - will likely fail but show signing
    )
    
    print(f"Order result: {result}")
    
    # Check if the order was placed by looking at the response
    if result.get('status') == 'ok':
        print("Order submitted successfully!")
        print("Checking which wallet the order was placed from...")
        
        # Check both wallets for new orders/positions
        agent_state = info.user_state(AGENT_WALLET)
        main_state = info.user_state(MAIN_WALLET)
        
        agent_positions = agent_state.get('assetPositions', [])
        main_positions = main_state.get('assetPositions', [])
        
        print(f"Agent wallet positions: {len(agent_positions)}")
        print(f"Main wallet positions: {len(main_positions)}")
        
        for pos in agent_positions:
            p = pos.get('position', {})
            print(f"  Agent - {p.get('coin')}: {p.get('szi')}")
        for pos in main_positions:
            p = pos.get('position', {})
            print(f"  Main - {p.get('coin')}: {p.get('szi')}")
            
except Exception as e:
    print(f"Order error (expected for tiny size): {e}")

# Test 6: Verify the signature is being created with correct wallet
print("\n--- Test 6: Signature Verification ---")
from hyperliquid.utils.signing import sign_l1_action, get_timestamp_ms

# Create a dummy action
test_action = {
    "type": "order",
    "orders": [],
    "grouping": "na",
    "builder": None
}

timestamp = get_timestamp_ms()
signature = sign_l1_action(
    agent_account,
    test_action,
    None,  # vault_address
    timestamp,
    None,  # expires_after
    False  # is_mainnet
)

print(f"Signature created: {signature[:20]}...")
print(f"Signing wallet: {agent_account.address}")

# The signature includes the wallet address implicitly via the signing process
print("\n" + "=" * 70)
print("DEBUG SUMMARY")
print("=" * 70)
print(f"✓ Account created from private key matches expected: {agent_account.address.lower() == AGENT_WALLET.lower()}")
print(f"✓ Exchange.wallet.address matches: {exchange.wallet.address.lower() == AGENT_WALLET.lower()}")
print("\nIf orders are still going to the main wallet, the issue is likely:")
print("1. The SDK's Exchange class is using some internal vault/subaccount logic")
print("2. There's a global state or cache issue")
print("3. The private key being used is actually the main wallet key")
print("=" * 70)
