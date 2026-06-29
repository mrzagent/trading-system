import json
from collections import Counter

with open('results/backtest_multitp_20260614_225519.json') as f:
    data = json.load(f)

print('='*70)
print('EXIT REASON BREAKDOWN')
print('='*70)
reasons = Counter(t['exit_reason'] for t in data['trades'])
for reason, count in reasons.most_common():
    pct = (count / len(data['trades'])) * 100
    print(f"  {reason}: {count} ({pct:.1f}%)")

print()
print('='*70)
print('FIRST 5 TRADES')
print('='*70)
for t in data['trades'][:5]:
    print(f"{t['entry_date'][:10]} | {t['symbol']} {t['direction'].upper()}")
    print(f"  Entry: ${t['entry_price']:,.2f}")
    print(f"  Exit:  ${t['exit_price']:,.2f}")
    print(f"  SL:    ${t['stop_loss']:,.2f}")
    print(f"  PnL:   ${t['pnl']:+.2f}")
    print(f"  Reason: {t['exit_reason']}")
    print(f"  TPs hit: {t['tp_levels_hit']}")
    
    # Calculate actual price move
    if t['direction'] == 'long':
        move = ((t['exit_price'] - t['entry_price']) / t['entry_price']) * 100
    else:
        move = ((t['entry_price'] - t['exit_price']) / t['entry_price']) * 100
    print(f"  Actual move: {move:+.2f}%")
    print()

print('='*70)
print('LAST 5 TRADES')
print('='*70)
for t in data['trades'][-5:]:
    print(f"{t['entry_date'][:10]} | {t['symbol']} | PnL: ${t['pnl']:+.2f} | {t['exit_reason']}")
