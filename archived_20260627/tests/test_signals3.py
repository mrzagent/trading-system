#!/usr/bin/env python3
"""Debug strategy signal generation."""

import sys
sys.path.insert(0, r'D:\dev\trading')

from datetime import datetime, timezone
from orchestrator import STRATEGY_CONFIG, load_strategy_state, is_strategy_enabled, run_strategy, analyse
from db import COINS, get_conn

print("=" * 60)
print("STRATEGY DEBUG")
print("=" * 60)

state = load_strategy_state()
print(f"\nStrategy state: {state}")
print(f"\nChecking each strategy:")
for name in STRATEGY_CONFIG:
    enabled = is_strategy_enabled(name, state)
    print(f"  {name}: {'ENABLED' if enabled else 'DISABLED'}")

print("\n" + "-" * 60)
print("Testing one strategy manually...")
print("-" * 60)

conn = get_conn()
candle_start = datetime.now(timezone.utc)
coin = "BTC"

# Test one strategy
name = "rsi_mean_reversion"
config = STRATEGY_CONFIG[name]
print(f"\nRunning {name} for {coin}...")
print(f"  Enabled: {is_strategy_enabled(name, state)}")

try:
    signal = run_strategy(name, config, coin, conn, candle_start)
    print(f"  Action: {signal.get('action')}")
    print(f"  Confidence: {signal.get('confidence')}")
    print(f"  Reason: {signal.get('reason', '')[:80]}")
except Exception as e:
    print(f"  ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "-" * 60)
print("Testing full analyse()...")
print("-" * 60)

try:
    result = analyse(coin, conn, candle_start)
    print(f"  Signal: {result.get('action')}")
    print(f"  Confidence: {result.get('confidence')}")
    print(f"  Strategies run: {result.get('metadata', {}).get('strategies_run')}")
    print(f"  Strategies total: {result.get('metadata', {}).get('strategies_total')}")
    print(f"  Disabled: {result.get('metadata', {}).get('strategies_disabled')}")
except Exception as e:
    print(f"  ERROR: {e}")
    import traceback
    traceback.print_exc()

conn.close()
