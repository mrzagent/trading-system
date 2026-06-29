#!/usr/bin/env python3
"""Debug strategy signal generation."""

import sys
sys.path.insert(0, r'D:\dev\trading')

from datetime import datetime, timezone
from orchestrator import STRATEGY_CONFIG, load_strategy_state, is_strategy_enabled, run_strategy, analyse
from db import COINS, get_conn
import json

print("=" * 60)
print("FULL SIGNAL TEST")
print("=" * 60)

conn = get_conn()
candle_start = datetime.now(timezone.utc)

for coin in COINS:
    print(f"\n>>> {coin}:")
    try:
        result = analyse(coin, conn, candle_start)
        # Pretty print without unicode issues
        print(f"  Signal: {result.get('action')}")
        print(f"  Confidence: {result.get('confidence')}")
        print(f"  Reason: {result.get('reason', '')[:100]}")
        meta = result.get('metadata', {})
        print(f"  Strategies run: {meta.get('strategies_run')}")
        print(f"  Strategies total: {meta.get('strategies_total')}")
        disabled = meta.get('strategies_disabled', [])
        print(f"  Disabled: {disabled if disabled else 'None'}")
        
        # Show breakdown
        breakdown = meta.get('strategy_breakdown', {})
        if breakdown:
            print(f"  Strategy signals:")
            for name, data in breakdown.items():
                action = data.get('action', 'HOLD')
                conf = data.get('confidence', 0)
                print(f"    - {name}: {action} ({conf:.2f})")
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()

conn.close()
print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)
