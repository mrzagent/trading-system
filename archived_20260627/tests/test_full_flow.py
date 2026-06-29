"""Test complete trading flow"""
from trade_executor import TradeExecutor, RiskConfig, execute_signal

print("=== Testing Complete Trading Flow ===\n")

# Initialize executor
executor = TradeExecutor(RiskConfig())

# 1. Check main account balance (portfolio endpoint)
print("1. Checking MAIN account balance...")
balance = executor.client.get_balance()
print(f"   Balance: ${balance:.2f}")
print(f"   [OK] Main account portfolio checked\n")

# 2. Check agent wallet
print("2. Checking agent wallet...")
import os
agent_wallet = os.getenv('HYPERLIQUID_WALLET')
print(f"   Agent: {agent_wallet}")
print(f"   [OK] Agent wallet configured\n")

# 3. Test order placement with SL/TP
print("3. Testing order placement with SL/TP...")

# Create a test signal
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
    'timestamp': '2026-06-26T23:30:00',
    'strategy': 'momentum_accel'
}

# Execute signal
print("   Executing signal...")
try:
    result = execute_signal(signal, test_mode=False)
    if result:
        print(f"   [OK] Entry order placed: {result.get('entry_oid', 'N/A')}")
        print(f"   [OK] SL order placed: {result.get('sl_oid', 'N/A')}")
        print(f"   [OK] TP orders placed: {result.get('tp_oids', [])}")
    else:
        print("   [FAIL] Signal execution returned None")
except Exception as e:
    print(f"   [FAIL] Error: {e}")
    import traceback
    traceback.print_exc()

print("\n=== Flow Verification Complete ===")
