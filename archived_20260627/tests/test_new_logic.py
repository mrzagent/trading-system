"""Test the new strategy-aware logic"""
import sys
sys.path.insert(0, r'D:\dev\trading')

from signal_integrator import SignalIntegrator
from trade_executor import RiskConfig

# Create integrator with 10 min cooldown (from settings)
integrator = SignalIntegrator(
    RiskConfig(), 
    test_mode=False, 
    allow_multiple_positions=False,
    cooldown_minutes=10  # Actual setting from file
)

print("Testing NEW strategy-aware logic:")
print(f"Open trades: {list(integrator.executor.open_trades.keys())}")

# Check existing SOL position strategy
if 'SOL' in integrator.executor.open_trades:
    trade = integrator.executor.open_trades['SOL']
    existing_strategy = trade.get('strategy') if isinstance(trade, dict) else getattr(trade, 'strategy', None)
    print(f"Existing SOL strategy: {existing_strategy}")
    print()

# Test 1: Same strategy (should be skipped)
print("Test 1: SAME strategy signal (momentum_accel):")
signal1 = {
    'coin': 'SOL',
    'action': 'BUY',
    'confidence': 0.8,
    'strategy': 'momentum_accel',
    'meta': {'price': 73.0, 'stop_loss_pct': 2.5, 'take_profit_pct': 5.0}
}
result1 = integrator.process_signal(signal1, dry_run=True)
print(f"  Result: {'ALLOWED' if result1 else 'SKIPPED'}")
print()

# Test 2: Different strategy (should be allowed since existing is None)
print("Test 2: DIFFERENT strategy signal (rsi_mean_reversion):")
signal2 = {
    'coin': 'SOL',
    'action': 'BUY',
    'confidence': 0.8,
    'strategy': 'rsi_mean_reversion',
    'meta': {'price': 73.0, 'stop_loss_pct': 2.5, 'take_profit_pct': 5.0}
}
result2 = integrator.process_signal(signal2, dry_run=True)
print(f"  Result: {'ALLOWED' if result2 else 'SKIPPED'}")
print()

print("Note: Existing position has strategy=None (old data)")
print("      New trades will store strategy correctly")
