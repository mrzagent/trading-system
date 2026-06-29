#!/usr/bin/env python3
"""Place a SOL LONG trade on Hyperliquid testnet using official SDK"""
import os
import sys
import json

# Load env vars
sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

from dotenv import load_dotenv
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants
from eth_account import Account

# Load credentials from .env
load_dotenv(r'C:\Users\mrztms\.openclaw\.env')

wallet_address = os.getenv('HYPERLIQUID_WALLET')
private_key = os.getenv('HYPERLIQUID_PRIVATE_KEY')

print("=" * 60)
print("HYPERLIQUID TESTNET - PLACE ORDER")
print("=" * 60)
print(f"\nWallet: {wallet_address}")

# Create wallet account
account = Account.from_key(private_key)

# Create exchange client (testnet)
exchange = Exchange(account, base_url=constants.TESTNET_API_URL)

# Get current SOL price
info = Info(constants.TESTNET_API_URL)
meta = info.meta()
sol_info = next((a for a in meta["universe"] if a["name"] == "SOL"), None)
if sol_info:
    sz_decimals = sol_info["szDecimals"]
    print(f"SOL szDecimals: {sz_decimals}")
else:
    sz_decimals = 2
    print(f"SOL info not found, using default szDecimals: {sz_decimals}")

# Get mid price
all_mids = info.all_mids()
sol_price = float(all_mids.get("SOL", 0))
print(f"Current SOL price: ${sol_price:,.2f}")

# Trade parameters
notional = 10.0  # $10 minimum
leverage = 10.0  # 10x

# Size in SOL coins - ensure minimum $10 notional
sz = round((notional + 0.5) / sol_price, sz_decimals)
actual_notional = sz * sol_price

# Place limit order (1% above current price to ensure fill)
limit_px = round(sol_price * 1.01, 2)
print(f"\nTrade Details:")
print(f"  Direction: LONG")
print(f"  Size: {sz} SOL")
print(f"  Notional: ${actual_notional:.2f}")
print(f"  Leverage: {leverage:.0f}x")
print(f"  Margin: ${actual_notional/leverage:.2f}")
print(f"  Order Type: Limit @ ${limit_px}")
print()

print(f"Placing limit order at ${limit_px} (1% above market)...")

result = exchange.order("SOL", True, sz, limit_px, {"limit": {"tif": "Gtc"}}, False)
print(f"\nResult: {json.dumps(result, indent=2)}")

if result.get("status") == "ok":
    print("\n[OK] Order placed successfully!")
    statuses = result.get("response", {}).get("data", {}).get("statuses", [])
    entry_px = None
    for status in statuses:
        if "filled" in status:
            filled = status["filled"]
            entry_px = float(filled.get('avgPx', 0))
            print(f"   Filled: {filled.get('totalSz')} @ ${entry_px}")
        elif "resting" in status:
            resting = status["resting"]
            print(f"   Resting: OID {resting.get('oid')}")
        elif "error" in status:
            print(f"   Error: {status['error']}")
    
    # Add Stop Loss and Take Profit orders
    if entry_px:
        print("\n" + "=" * 60)
        print("SETTING STOP LOSS & TAKE PROFIT")
        print("=" * 60)
        
        # SL: -5% from entry (50% loss on 10x)
        sl_pct = 0.05
        sl_px = round(entry_px * (1 - sl_pct), 2)
        
        # TP: +10% from entry (100% profit on 10x)
        tp_pct = 0.10
        tp_px = round(entry_px * (1 + tp_pct), 2)
        
        print(f"\nEntry Price: ${entry_px}")
        print(f"Stop Loss:   ${sl_px} (-{sl_pct*100:.0f}%, -{sl_pct*leverage*100:.0f}% on position)")
        print(f"Take Profit: ${tp_px} (+{tp_pct*100:.0f}%, +{tp_pct*leverage*100:.0f}% on position)")
        print()
        
        # Place Stop Loss (stop market order - sell stop)
        print("Placing Stop Loss...")
        sl_result = exchange.order(
            "SOL", 
            False,  # is_buy = False (sell)
            sz, 
            sl_px,  # trigger price
            {"trigger": {"isMarket": True, "triggerPx": sl_px, "tpsl": "sl"}},
            True    # reduce_only = True
        )
        print(f"SL Result: {json.dumps(sl_result, indent=2)}")
        
        # Place Take Profit (limit order - sell limit)
        print("\nPlacing Take Profit...")
        tp_result = exchange.order(
            "SOL", 
            False,  # is_buy = False (sell)
            sz, 
            tp_px,  # limit price
            {"limit": {"tif": "Gtc"}},
            True    # reduce_only = True
        )
        print(f"TP Result: {json.dumps(tp_result, indent=2)}")
        
        print("\n[OK] SL/TP orders placed!")
else:
    print(f"\n[X] Order failed: {result}")
