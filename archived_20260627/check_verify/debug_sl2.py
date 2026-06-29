import json

with open('results/backtest_multitp_20260614_225519.json') as f:
    data = json.load(f)

# Check the relationship between entry and SL
t = data['trades'][0]
print(f"Entry: {t['entry_price']}")
print(f"SL: {t['stop_loss']}")
print(f"Direction: {t['direction']}")
print(f"SL - Entry: {t['stop_loss'] - t['entry_price']}")

# Check if SL was moved to breakeven
print(f"Breakeven hit: {t['breakeven_hit']}")

# Check partial closes
print(f"Partial closes: {t['partial_closes']}")

# Check raw price data - maybe prices just went straight up?
# Let's see the first trade's take_profits to verify
print(f"\nTake profits for first trade:")
for tp in t['take_profits']:
    print(f"  {tp['label']}: ${tp['price']:.2f} (hit: {tp['hit']})")

# Calculate what SL should have been
expected_sl = t['entry_price'] * 0.95  # 5% SL
print(f"\nExpected SL (5% below entry): ${expected_sl:.2f}")
print(f"Actual SL: ${t['stop_loss']:.2f}")

# Check a few more trades
print("\n\nChecking first 10 trades:")
for i, t in enumerate(data['trades'][:10]):
    entry = t['entry_price']
    sl = t['stop_loss']
    expected = entry * 0.95
    diff_pct = ((sl - entry) / entry) * 100
    print(f"{i+1}. {t['symbol']}: Entry=${entry:.2f}, SL=${sl:.2f}, Diff={diff_pct:+.2f}%, Expected=${expected:.2f}")
