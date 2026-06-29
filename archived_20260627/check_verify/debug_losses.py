import json

with open('results/backtest_multitp_20260614_225519.json') as f:
    data = json.load(f)

# Check for any negative PnL trades
losses = [t for t in data['trades'] if t['pnl'] < 0]
wins = [t for t in data['trades'] if t['pnl'] > 0]

print(f"Total trades: {len(data['trades'])}")
print(f"Winning trades: {len(wins)}")
print(f"Losing trades: {len(losses)}")

if losses:
    print(f"\nLosing trades sample:")
    for t in losses[:5]:
        print(f"  {t['symbol']} | PnL: ${t['pnl']:.2f} | {t['exit_reason']}")
else:
    print("\nNo losing trades found!")

# Check distribution of PnL
pnls = [t['pnl'] for t in data['trades']]
print(f"\nPnL stats:")
print(f"  Min: ${min(pnls):.2f}")
print(f"  Max: ${max(pnls):.2f}")
print(f"  Avg: ${sum(pnls)/len(pnls):.2f}")

# Check exit reasons
from collections import Counter
reasons = Counter(t['exit_reason'] for t in data['trades'])
print(f"\nExit reasons:")
for r, c in reasons.items():
    print(f"  {r}: {c}")

# The issue might be that with max_bars=576, prices always recover
# Let's check the data date range
print(f"\nData range:")
dates = [t['entry_date'][:10] for t in data['trades']]
print(f"  First: {min(dates)}")
print(f"  Last: {max(dates)}")
