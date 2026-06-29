from trade_executor import TradeExecutor, RiskConfig

executor = TradeExecutor(RiskConfig())
print(f"Balance: ${executor.client.get_balance():.2f}")

result = executor.client.place_order('SOL', True, 1.0, 80.0, 'Market')
print(f"Order result: {result}")
