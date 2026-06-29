from trade_executor import TradeExecutor, RiskConfig
import logging
logging.basicConfig(level=logging.DEBUG)

executor = TradeExecutor(RiskConfig())

print("Testing open_position_real...")
try:
    result = executor.open_position_real(
        symbol='SOL',
        side='long',
        sz=1.0,  # Small size for test
        limit_px=73.0,
        order_type='Market',
        stop_loss=71.0,
        take_profits=[76.0]
    )
    print(f"Result: {result}")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
