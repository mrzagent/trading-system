"""Check why the SOL signal was skipped"""
from signal_integrator import SignalIntegrator
from trade_executor import RiskConfig
import json
from datetime import datetime

# Create integrator with correct settings
integrator = SignalIntegrator(
    RiskConfig(), 
    test_mode=False, 
    allow_multiple_positions=False,
    cooldown_minutes=10
)

print("Checking why SOL signal was skipped...")
print(f"Current time: {datetime.now().strftime('%H:%M:%S')}")
print()

# Check open trades
print(f"Open trades: {list(integrator.executor.open_trades.keys())}")
if 'SOL' in integrator.executor.open_trades:
    trade = integrator.executor.open_trades['SOL']
    strategy = trade.get('strategy') if isinstance(trade, dict) else getattr(trade, 'strategy', None)
    entry_time = trade.get('entry_time') if isinstance(trade, dict) else getattr(trade, 'entry_time', None)
    print(f"Existing SOL trade:")
    print(f"  Strategy: {strategy}")
    print(f"  Entry time: {entry_time}")
    
    # Check if cooldown applies
    if entry_time:
        entry = datetime.fromisoformat(entry_time)
        now = datetime.now()
        minutes_ago = (now - entry).total_seconds() / 60
        print(f"  Minutes ago: {minutes_ago:.1f}")
        print(f"  Cooldown: 10 minutes")
        print(f"  In cooldown: {minutes_ago < 10}")
print()

# Check signal history
print("Checking signal trade history...")
with open('signal_trade_history.json', 'r') as f:
    history = json.load(f)

# Find last SOL trade in history
for trade in reversed(history):
    if trade.get('coin') == 'SOL':
        trade_time = datetime.fromisoformat(trade.get('timestamp'))
        now = datetime.now()
        minutes_ago = (now - trade_time).total_seconds() / 60
        print(f"Last SOL in history: {trade.get('strategy')} at {trade_time.strftime('%H:%M:%S')} ({minutes_ago:.1f}m ago)")
        print(f"In cooldown: {minutes_ago < 10}")
        break

print()

# Simulate the signal
signal = {
    'coin': 'SOL',
    'action': 'BUY',
    'confidence': 0.76,
    'strategy': 'momentum_accel',
    'reason': 'Momentum accelerating: 5.47% ROC with +0.51% acceleration',
    'meta': {
        'price': 72.5,
        'stop_loss_pct': 2.5,
        'take_profit_pct': 5.0
    }
}

print("Testing signal processing...")
result = integrator.process_signal(signal, dry_run=True)
print(f"Result: {'WOULD EXECUTE' if result else 'SKIPPED'}")
