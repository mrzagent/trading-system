#!/usr/bin/env python3
"""Test if strategies are generating signals from database."""

import sys
sys.path.insert(0, r'D:\dev\trading')

from datetime import datetime, timezone
from orchestrator import analyse, load_strategy_state, STRATEGY_CONFIG
from db import COINS, get_conn

print("=" * 60)
print("SIGNAL GENERATION TEST")
print("=" * 60)
print(f"\nCoins: {COINS}")
print(f"Total strategies in config: {len(STRATEGY_CONFIG)}")

# Load strategy state
state = load_strategy_state()
print(f"\nStrategy state file loaded: {len(state)} entries")
for name, enabled in state.items():
    status = "ON" if enabled else "OFF"
    print(f"  [{status}] {name}")

print("\n" + "-" * 60)
print("Running orchestrator for each coin...")
print("-" * 60)

conn = get_conn()
candle_start = datetime.now(timezone.utc)

for coin in COINS:
    print(f"\n>>> {coin}:")
    try:
        result = analyse(coin, conn, candle_start)
        signal = result.get('signal', 'ERROR')
        confidence = result.get('confidence', 0)
        strategies_run = result.get('metadata', {}).get('strategies_run', 0)
        strategies_total = result.get('metadata', {}).get('strategies_total', 0)
        strategies_disabled = result.get('metadata', {}).get('strategies_disabled', [])
        
        print(f"  Signal: {signal} (confidence: {confidence:.2f})")
        print(f"  Strategies run: {strategies_run}/{strategies_total}")
        if strategies_disabled:
            print(f"  Disabled: {', '.join(strategies_disabled)}")
        
        # Show individual strategy signals
        strategy_signals = result.get('metadata', {}).get('strategy_signals', {})
        if strategy_signals:
            print(f"  Individual signals:")
            for name, sig in strategy_signals.items():
                print(f"    - {name}: {sig}")
        
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()

conn.close()

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)
