#!/usr/bin/env python3
"""Test the signal executor"""
import sys
import os

sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

from signal_executor import SignalExecutor

executor = SignalExecutor()

# Check existing positions
print("Current positions:")
for coin in ['BTC', 'ETH', 'SOL']:
    pos = executor.get_position(coin)
    if pos and pos['size'] != 0:
        print(f"  {coin}: {pos['size']:.4f} @ ${pos['entry_px']:.2f}")
    else:
        print(f"  {coin}: None")

print("\nOpen orders for SOL:")
orders = executor.get_open_orders('SOL')
for o in orders:
    oid = o.get('oid', 'N/A')
    side = 'SELL' if not o.get('isBuy') else 'BUY'
    sz = o.get('sz', 0)
    limit_px = o.get('limitPx', 0)
    trigger_px = o.get('triggerPx')
    is_trigger = o.get('isTrigger', False)
    reduce_only = o.get('reduceOnly', False)
    
    if reduce_only:
        order_type = "TP" if not is_trigger else "SL"
        px_str = f"Trigger: ${float(trigger_px):.2f}" if trigger_px else f"Limit: ${float(limit_px):.2f}"
        print(f"  [{order_type}] {side} {sz} @ {px_str} (OID: {oid})")

print("\n[OK] Executor test complete")
