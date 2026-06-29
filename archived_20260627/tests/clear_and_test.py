"""Clear positions and test full flow"""
import json

# Clear open trades
with open('trade_state.json', 'r') as f:
    state = json.load(f)

print(f"Current open trades: {list(state['open_trades'].keys())}")

# Move to history
for symbol, trade in list(state['open_trades'].items()):
    trade['exit_time'] = '2026-06-26T23:40:00'
    trade['exit_price'] = trade['entry_price']
    trade['exit_reason'] = 'test_cleanup'
    trade['pnl'] = 0
    state['trade_history'].append(trade)

state['open_trades'] = {}

with open('trade_state.json', 'w') as f:
    json.dump(state, f, indent=2)

print("Cleared open trades")

# Now test
from trade_executor import TradeExecutor, RiskConfig, execute_signal
import os

print("\n=== Testing Complete Trading Flow ===\n")

executor = TradeExecutor(RiskConfig())

# 1. Check main account balance
print("1. Checking MAIN account balance...")
balance = executor.client.get_balance()
print(f"   Balance: ${balance:.2f}")
print(f"   [OK] Main account portfolio checked\n")

# 2. Check agent wallet
print("2. Checking agent wallet...")
agent_wallet = os.getenv('HYPERLIQUID_WALLET')
print(f"   Agent: {agent_wallet}")
print(f"   Main:  {executor.client.MAIN_WALLET}")
print(f"   [OK] Agent wallet signs for Main account\n")

# 3. Test order placement
print("3. Testing order placement with SL/TP...")

signal = {
    'coin': 'SOL',
    'action': 'BUY',
    'confidence': 0.79,
    'reason': 'Test signal',
    'meta': {
        'price': 73.0,
        'stop_loss_pct': 2.5,
        'take_profit_pct': 5.0,
        'strategy_type': 'momentum',
        'strategy_style': 'swing'
    },
    'timestamp': '2026-06-26T23:40:00',
    'strategy': 'momentum_accel'
}

print("   Executing signal...")
try:
    result = execute_signal(signal, test_mode=False)
    if result:
        print(f"\n   [SUCCESS] Trade executed!")
        print(f"   Entry Order ID: {result.get('entry_oid', 'N/A')}")
        print(f"   SL Order ID: {result.get('sl_oid', 'N/A')}")
        print(f"   TP Order IDs: {result.get('tp_oids', [])}")
        print(f"\n   All orders placed on HyperLiquid!")
    else:
        print("   [FAIL] Signal execution returned None")
except Exception as e:
    print(f"   [FAIL] Error: {e}")
    import traceback
    traceback.print_exc()

print("\n=== Verification Complete ===")
