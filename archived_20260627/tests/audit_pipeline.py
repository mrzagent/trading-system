"""Audit the entire signal-to-trade pipeline"""
import sys
sys.path.insert(0, r'D:\dev\trading')

print("="*60)
print("SIGNAL TO TRADE PIPELINE AUDIT")
print("="*60)

# 1. Check signals in database
print("\n1. DATABASE SIGNALS (Last 10 BUY/SELL):")
import urllib.request
import json
try:
    url = 'http://localhost:3001/api/trading/signals?page=1&limit=10&action=ALL&minConfidence=0.5'
    with urllib.request.urlopen(url) as res:
        data = json.loads(res.read().decode())
        for sig in data.get('signals', [])[:5]:
            if sig.get('action') in ['BUY', 'SELL']:
                print(f"   {sig.get('coin')} {sig.get('action')} {sig.get('confidence',0)*100:.0f}% | {sig.get('strategy')} | {sig.get('created_at')}")
except Exception as e:
    print(f"   ERROR: {e}")

# 2. Check trade executor configuration
print("\n2. TRADE EXECUTOR CONFIG:")
from trade_executor import TradeExecutor, ETH_ACCOUNT_AVAILABLE
print(f"   ETH_ACCOUNT_AVAILABLE: {ETH_ACCOUNT_AVAILABLE}")

import os
from dotenv import load_dotenv
load_dotenv(os.path.expanduser('~/.openclaw/.env'))
wallet = os.getenv('HYPERLIQUID_WALLET')
key = os.getenv('HYPERLIQUID_PRIVATE_KEY')
print(f"   Wallet configured: {wallet is not None}")
print(f"   Key configured: {key is not None}")

# 3. Check SignalIntegrator
print("\n3. SIGNAL INTEGRATOR:")
from signal_integrator import SignalIntegrator
from trade_executor import RiskConfig

integrator = SignalIntegrator(
    risk_config=RiskConfig(),
    test_mode=False,
    min_confidence=0.5,
    cooldown_minutes=30,
    allow_multiple_positions=False
)
print(f"   test_mode: {integrator.test_mode}")
print(f"   min_confidence: {integrator.min_confidence}")
print(f"   cooldown_minutes: {integrator.cooldown_minutes}")

# 4. Check trade state
print("\n4. TRADE STATE:")
import json as json_mod
try:
    with open('trade_state.json', 'r') as f:
        state = json_mod.load(f)
    open_trades = state.get('open_trades', {})
    history = state.get('trade_history', [])
    print(f"   Open trades: {len(open_trades)}")
    for sym, trade in open_trades.items():
        print(f"      {sym}: {trade['side']} @ {trade['entry_price']}")
    print(f"   Trade history count: {len(history)}")
    if history:
        last = history[-1]
        print(f"   Last trade: {last['symbol']} {last['side']} @ {last['entry_time']}")
except Exception as e:
    print(f"   ERROR: {e}")

# 5. Check account settings
print("\n5. ACCOUNT SETTINGS:")
settings_path = '.account_settings.json'
if os.path.exists(settings_path):
    with open(settings_path, 'r') as f:
        settings = json_mod.load(f)
    print(f"   cooldownMinutes: {settings.get('cooldownMinutes')}")
    print(f"   allowMultiplePositions: {settings.get('allowMultiplePositions')}")
    print(f"   minConfidence: {settings.get('minConfidence')}")
else:
    print("   No settings file")

# 6. Try to execute a test signal
print("\n6. TEST SIGNAL EXECUTION:")
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

try:
    result = integrator.process_signal(test_signal, dry_run=True)
    print(f"   Test result: {result}")
except Exception as e:
    print(f"   ERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*60)
