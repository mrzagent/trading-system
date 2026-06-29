from trade_executor import TradeExecutor, RiskConfig

executor = TradeExecutor(RiskConfig())
positions = executor.client.get_positions()

print(f'HyperLiquid Positions: {len(positions)}')
for pos in positions:
    print(f"  {pos['coin']}: {pos['side']} {pos['size']} @ ${pos['entry_px']}")
