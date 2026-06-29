"""Test live trade execution"""
import sys
sys.path.insert(0, r'D:\dev\trading')

from trade_executor import execute_signal
import logging
logging.basicConfig(level=logging.DEBUG)

test_signal = {
    'strategy': 'momentum_accel',
    'coin': 'SOL',
    'action': 'BUY',
    'confidence': 0.95,
    'reason': 'Test signal',
    'meta': {
        'price': 70.0,
        'candle': '2026-06-26T20:00:00',
        'stop_loss_pct': 2.5,
        'take_profit_pct': 5.0,
        'strategy_type': 'momentum',
        'strategy_style': 'swing'
    },
    'generated_at': '2026-06-26T20:25:00'
}

print("Testing LIVE trade execution...")
print("="*60)

try:
    result = execute_signal(test_signal, test_mode=False)
    print(f"\nResult: {result}")
except Exception as e:
    print(f"\nERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
