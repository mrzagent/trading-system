"""Verify orders on HyperLiquid"""
from trade_executor import TradeExecutor, RiskConfig

executor = TradeExecutor(RiskConfig())

print("Checking HyperLiquid orders...")
print(f"Main wallet: {executor.client.MAIN_WALLET}")

# Check positions
positions = executor.client.get_positions()
print(f"\nOpen Positions: {len(positions)}")
for p in positions:
    print(f"  {p['coin']}: {p['size']} @ ${p['entry_px']}")

# Check balance
balance = executor.client.get_balance()
print(f"\nBalance: ${balance:.2f}")
