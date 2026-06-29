import json
import urllib.request
from datetime import datetime, timezone

# Check latest signals
url = 'http://localhost:3001/api/trading/signals?page=1&limit=5&action=BUY&minConfidence=0.5'
with urllib.request.urlopen(url) as res:
    data = json.loads(res.read().decode())
    print('Latest BUY signals:')
    for sig in data.get('signals', [])[:3]:
        coin = sig.get('coin')
        action = sig.get('action')
        conf = sig.get('confidence', 0) * 100
        strat = sig.get('strategy')
        created = sig.get('created_at')
        notes = sig.get('notes', '')[:60]
        print(f"  {coin} | {action} | {conf:.0f}% | {strat}")
        print(f"    Time: {created}")
        print(f"    Notes: {notes}")
        print()

# Check if trade_state has any recent open trades
print('\nChecking trade_state.json...')
import os
state_path = os.path.join(os.path.dirname(__file__), 'trade_state.json')
if os.path.exists(state_path):
    with open(state_path, 'r') as f:
        state = json.load(f)
    open_trades = state.get('open_trades', {})
    if open_trades:
        print(f"Open trades: {len(open_trades)}")
        for symbol, trade in open_trades.items():
            print(f"  {symbol}: {trade.get('side')} @ {trade.get('entry_price')}")
    else:
        print("No open trades")
    
    history = state.get('trade_history', [])
    if history:
        last_trade = history[-1]
        print(f"\nLast trade: {last_trade.get('symbol')} {last_trade.get('side')} @ {last_trade.get('entry_time')}")
else:
    print("No trade_state.json found")
