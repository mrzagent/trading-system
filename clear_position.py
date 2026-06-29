import json

with open('trade_state.json', 'r') as f:
    state = json.load(f)

# Move open trades to history
for symbol, trade in list(state['open_trades'].items()):
    trade['exit_time'] = '2026-06-26T23:07:00'
    trade['exit_price'] = trade['entry_price']
    trade['exit_reason'] = 'manual_close'
    trade['pnl'] = 0
    state['trade_history'].append(trade)

state['open_trades'] = {}

with open('trade_state.json', 'w') as f:
    json.dump(state, f, indent=2)

print('Cleared open positions')
