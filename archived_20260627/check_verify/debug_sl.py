import json

with open('results/backtest_multitp_20260614_223455.json') as f:
    data = json.load(f)

# Find trades with negative PnL that should have hit SL
losses = [t for t in data['trades'] if t['pnl'] < -2]

print(f"Trades with PnL < -$2: {len(losses)}")
print()

if losses:
    print("Sample loss trades:")
    for t in losses[:5]:
        pct_move = ((t['exit_price'] - t['entry_price']) / t['entry_price']) * 100
        if t['direction'] == 'short':
            pct_move = -pct_move
        print(f"  {t['symbol']} {t['direction'].upper()}")
        print(f"    Entry: ${t['entry_price']:,.2f}")
        print(f"    Exit:  ${t['exit_price']:,.2f}")
        print(f"    SL:    ${t['stop_loss']:,.2f}")
        print(f"    Move:  {pct_move:+.2f}%")
        print(f"    PnL:   ${t['pnl']:+.2f}")
        print(f"    Exit reason: {t['exit_reason']}")
        print()

# Check if SL is in right direction
print("Checking SL direction for long trades:")
long_trades = [t for t in data['trades'] if t['direction'] == 'long'][:5]
for t in long_trades:
    sl_pct = ((t['stop_loss'] - t['entry_price']) / t['entry_price']) * 100
    print(f"  {t['symbol']}: Entry ${t['entry_price']:,.2f}, SL ${t['stop_loss']:,.2f} ({sl_pct:+.2f}%)")

print()
print("Checking SL direction for short trades:")
short_trades = [t for t in data['trades'] if t['direction'] == 'short'][:5]
for t in short_trades:
    sl_pct = ((t['stop_loss'] - t['entry_price']) / t['entry_price']) * 100
    print(f"  {t['symbol']}: Entry ${t['entry_price']:,.2f}, SL ${t['stop_loss']:,.2f} ({sl_pct:+.2f}%)")
