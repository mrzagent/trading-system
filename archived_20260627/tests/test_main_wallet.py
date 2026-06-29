from trade_executor import TradeExecutor, RiskConfig

executor = TradeExecutor(RiskConfig())
balance = executor.client.get_balance()
positions = executor.client.get_positions()

print(f'Balance from MAIN wallet: ${balance:.2f}')
print(f'Positions: {len(positions)}')
for pos in positions:
    print(f"  {pos['coin']}: {pos['size']} @ ${pos['entry_px']}")
