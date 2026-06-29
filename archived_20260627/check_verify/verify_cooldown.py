"""Verify cooldown settings"""
import json

# Load account settings
with open('.account_settings.json', 'r') as f:
    settings = json.load(f)

print("Account Settings:")
print(f"  cooldownMinutes: {settings.get('cooldownMinutes')}")
print(f"  allowMultiplePositions: {settings.get('allowMultiplePositions')}")

# Load signal history to check last trade
with open('signal_trade_history.json', 'r') as f:
    history = json.load(f)

# Find last SOL trade
for trade in reversed(history):
    if trade.get('coin') == 'SOL':
        from datetime import datetime
        trade_time = datetime.fromisoformat(trade.get('timestamp'))
        now = datetime.now()
        minutes_ago = (now - trade_time).total_seconds() / 60
        print(f"\nLast SOL trade: {trade_time}")
        print(f"Minutes ago: {minutes_ago:.1f}")
        print(f"Cooldown: {settings.get('cooldownMinutes')} minutes")
        print(f"Remaining: {max(0, settings.get('cooldownMinutes', 10) - minutes_ago):.1f} minutes")
        break
