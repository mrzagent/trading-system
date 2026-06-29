import json

with open('results/backtest_multitp_20260614_225519.json') as f:
    data = json.load(f)

# Find the 4 stop_loss trades
sl_trades = [t for t in data['trades'] if t['exit_reason'] == 'stop_loss']

print(f"Stop loss trades: {len(sl_trades)}")
for t in sl_trades:
    print(f"\n{t['symbol']} {t['direction'].upper()}")
    print(f"  Entry: ${t['entry_price']:,.2f}")
    print(f"  Exit:  ${t['exit_price']:,.2f}")
    print(f"  SL:    ${t['stop_loss']:,.2f}")
    print(f"  PnL:   ${t['pnl']:+.2f}")
    print(f"  TPs hit: {t['tp_levels_hit']}")
    print(f"  Breakeven: {t['breakeven_hit']}")
    
    # Calculate what happened
    if t['direction'] == 'long':
        move = ((t['exit_price'] - t['entry_price']) / t['entry_price']) * 100
    else:
        move = ((t['entry_price'] - t['exit_price']) / t['entry_price']) * 100
    print(f"  Price move: {move:+.2f}%")
    
    if t['partial_closes']:
        total_from_partials = sum(pc['pnl'] for pc in t['partial_closes'])
        print(f"  PnL from partials: ${total_from_partials:+.2f}")
        for pc in t['partial_closes']:
            print(f"    {pc['level']}: ${pc['pnl']:+.2f}")
