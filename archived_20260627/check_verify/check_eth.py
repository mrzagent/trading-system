import json
with open('trade_state.json', 'r') as f:
    state = json.load(f)
open_trades = state.get('open_trades', {})
history = state.get('trade_history', [])

print('Open positions:')
for symbol, trade in open_trades.items():
    print(f'  {symbol}: {trade["side"]} @ {trade["entry_price"]}')

print('\nRecent ETH trades:')
eth_trades = [t for t in history if t['symbol'] == 'ETH'][-3:]
for t in eth_trades:
    print(f'  {t["side"]} @ {t["entry_time"]} -> {t["exit_time"]} ({t["exit_reason"]}), PnL: {t.get("pnl", 0):.2f}')
