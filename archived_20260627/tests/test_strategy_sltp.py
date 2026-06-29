#!/usr/bin/env python3
"""Test that orchestrator includes strategy-specific SL/TP in signals."""

import sys
sys.path.insert(0, r'D:\dev\trading')

from datetime import datetime, timezone
from orchestrator import analyse, get_conn, COINS
from strategy_risk_config import get_strategy_risk_params, STRATEGY_RISK_PARAMS

print("=" * 70)
print("STRATEGY-SPECIFIC SL/TP TEST")
print("=" * 70)

# Show all strategy risk params
print("\n[1] CONFIGURED STRATEGY RISK PARAMETERS")
print("-" * 70)
for strategy_id, params in STRATEGY_RISK_PARAMS.items():
    print(f"  {strategy_id:20}: SL={params.stop_loss_pct*100:5.2f}%, TP={params.take_profit_pct*100:5.2f}%", end="")
    if params.use_atr:
        print(f" (ATR: SL={params.atr_sl_mult}x, TP={params.atr_tp_mult}x)")
    else:
        print()

# Run orchestrator and check signals include SL/TP
print("\n[2] ORCHESTRATOR SIGNALS WITH SL/TP")
print("-" * 70)

conn = get_conn()
candle_start = datetime.now(timezone.utc)

for coin in COINS:
    result = analyse(coin, conn, candle_start)
    
    action = result.get('action', 'HOLD')
    confidence = result.get('confidence', 0)
    meta = result.get('meta', {})
    
    sl = meta.get('stop_loss_pct', 'N/A')
    tp = meta.get('take_profit_pct', 'N/A')
    dominant = meta.get('dominant_strategy', 'unknown')
    use_atr = meta.get('use_atr', False)
    
    print(f"\n  {coin}:")
    print(f"    Signal: {action} ({confidence:.0%})")
    print(f"    Dominant Strategy: {dominant}")
    if use_atr:
        atr_sl = meta.get('atr_sl_mult', 'N/A')
        atr_tp = meta.get('atr_tp_mult', 'N/A')
        print(f"    SL/TP: ATR-based (SL={atr_sl}x, TP={atr_tp}x)")
    else:
        print(f"    SL/TP: {sl}% / {tp}%")
    
    # Verify against expected params
    expected = get_strategy_risk_params(dominant)
    if not use_atr and sl != 'N/A':
        expected_sl = expected.stop_loss_pct * 100
        expected_tp = expected.take_profit_pct * 100
        if abs(float(sl) - expected_sl) < 0.01 and abs(float(tp) - expected_tp) < 0.01:
            print(f"    [OK] Matches expected params")
        else:
            print(f"    [WARN] Mismatch! Expected: SL={expected_sl}%, TP={expected_tp}%")

conn.close()

print("\n" + "=" * 70)
print("TEST COMPLETE")
print("=" * 70)
print("""
The orchestrator now includes strategy-specific SL/TP in signal metadata:
- 'stop_loss_pct': Stop loss percentage (e.g., 1.5 for 1.5%)
- 'take_profit_pct': Take profit percentage (e.g., 3.0 for 3%)
- 'use_atr': Whether to use ATR-based stops
- 'atr_sl_mult': ATR multiplier for stop loss (if use_atr=True)
- 'atr_tp_mult': ATR multiplier for take profit (if use_atr=True)
- 'dominant_strategy': Which strategy determined the SL/TP

The signal_integrator will use these values when executing trades.
""")
