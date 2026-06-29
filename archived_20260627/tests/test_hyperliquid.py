#!/usr/bin/env python3
"""Test Hyperliquid testnet connection and show balance"""
import os
import sys

# Load env vars
sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

from trade_executor import HyperliquidClient
from dotenv import load_dotenv

# Load credentials from .env
load_dotenv(r'C:\Users\mrztms\.openclaw\.env')

wallet = os.getenv('HYPERLIQUID_WALLET')
private_key = os.getenv('HYPERLIQUID_PRIVATE_KEY')

print("=" * 60)
print("HYPERLIQUID TESTNET CONNECTION TEST")
print("=" * 60)
print(f"\nWallet: {wallet}")

# Create client
client = HyperliquidClient(wallet_address=wallet, private_key=private_key)

# Test connection - get clearinghouse state
print("\n[+] Pinging Hyperliquid API...")
try:
    response = client.get_user_state()
    
    print("[OK] API Connection successful!")
    print("\n" + "=" * 60)
    print("ACCOUNT BALANCE")
    print("=" * 60)
    
    # Extract balance info
    if 'assetPositions' in response and response['assetPositions']:
        print(f"\n[$] Open Positions: {len(response['assetPositions'])}")
        for pos in response['assetPositions']:
            position = pos.get('position', {})
            coin = position.get('coin', 'Unknown')
            size = position.get('szi', 0)
            entry_px = position.get('entryPx', 0)
            unrealized_pnl = position.get('unrealizedPnl', 0)
            print(f"  - {coin}: {size} @ ${float(entry_px):,.2f} (PnL: ${float(unrealized_pnl):.2f})")
    else:
        print("\n[$] Open Positions: None")
    
    # Account value
    margin_summary = response.get('marginSummary', {})
    account_value = margin_summary.get('accountValue', 'N/A')
    total_margin_used = margin_summary.get('totalMarginUsed', 'N/A')
    withdrawable = response.get('withdrawable', 'N/A')
    
    print(f"\n[#] Account Value: ${account_value}")
    print(f"[#] Margin Used: ${total_margin_used}")
    print(f"[#] Withdrawable: ${withdrawable}")
    
    # Get current balance specifically
    balance = client.get_balance()
    print(f"[#] USDC Balance: ${balance:.2f}")
    
    # Get mid prices for trading
    print("\n" + "=" * 60)
    print("CURRENT PRICES")
    print("=" * 60)
    try:
        mids = client.get_all_mids()
        for coin in ['BTC', 'ETH', 'SOL']:
            price = mids.get(coin, 0)
            if price:
                print(f"[#] {coin}: ${float(price):,.2f}")
            else:
                print(f"[#] {coin}: N/A")
    except Exception as e:
        print(f"[X] Error getting prices: {e}")
    
    print("\n" + "=" * 60)
    print("READY FOR TRADING")
    print("=" * 60)
    
except Exception as e:
    print(f"[X] API Error: {e}")
    import traceback
    traceback.print_exc()
