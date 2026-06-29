"""Check why trade wasn't placed"""
import sys
sys.path.insert(0, r'D:\dev\trading')

from trade_executor import TradeExecutor, RiskConfig, execute_signal
from signal_integrator import SignalIntegrator

print("="*60)
print("WHY NO TRADE?")
print("="*60)

# Check balance
executor = TradeExecutor(RiskConfig())
balance = executor.client.get_balance()
print(f"\n1. MAIN Wallet Balance: ${balance:.2f}")

# Check positions
positions = executor.client.get_positions()
print(f"2. Open Positions: {len(positions)}")
for pos in positions:
    print(f"   {pos['coin']}: {pos['side']} {pos['size']} @ ${pos['entry_px']}")

# Check cooldown
integrator = SignalIntegrator(
    risk_config=RiskConfig(),
    test_mode=False,
    min_confidence=0.5,
    cooldown_minutes=30,
    allow_multiple_positions=False
)

# Check if SOL is in cooldown
import json
try:
    with open('trade_state.json', 'r') as f:
        state = json.load(f)
    history = state.get('trade_history', [])
    sol_trades = [t for t in history if t['symbol'] == 'SOL'][-1:]
    if sol_trades:
        last = sol_trades[0]
        from datetime import datetime, timezone
        last_time = datetime.fromisoformat(last['entry_time'])
        now = datetime.now(timezone.utc)
        mins_ago = (now - last_time.replace(tzinfo=timezone.utc)).total_seconds() / 60
        print(f"\n3. Last SOL trade: {last['side']} @ {last['entry_time']} ({mins_ago:.0f} min ago)")
        print(f"   Cooldown remaining: {max(0, 30 - mins_ago):.0f} min")
except Exception as e:
    print(f"\n3. Could not check cooldown: {e}")

# Test the signal
test_signal = {
    'strategy': 'momentum_accel',
    'coin': 'SOL',
    'action': 'BUY',
    'confidence': 0.79,
    'reason': 'Momentum accelerating: 4.95% ROC with +0.97% acceleration',
    'meta': {
        'price': 70.0,
        'stop_loss_pct': 2.5,
        'take_profit_pct': 5.0,
        'strategy_type': 'momentum',
        'strategy_style': 'swing'
    },
    'generated_at': '2026-06-26T23:03:00'
}

print(f"\n4. Testing signal processing...")
result = integrator.process_signal(test_signal, dry_run=True)
print(f"   Result: {result}")
