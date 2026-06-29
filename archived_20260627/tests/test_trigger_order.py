"""Test trigger order placement"""
from trade_executor import TradeExecutor, RiskConfig

executor = TradeExecutor(RiskConfig())

print("Testing trigger order placement...")

# Test SL order
try:
    result = executor.client.place_trigger_order(
        coin='SOL',
        is_buy=False,  # Sell for SL on long
        sz=2.0,
        trigger_px=71.0,
        limit_px=70.0,
        tpsl='sl',
        is_market=True,
        reduce_only=True
    )
    print(f"SL Order Result: {result}")
except Exception as e:
    print(f"SL Order Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*50 + "\n")

# Test TP order
try:
    result = executor.client.place_trigger_order(
        coin='SOL',
        is_buy=False,  # Sell for TP on long
        sz=2.0,
        trigger_px=77.0,
        limit_px=76.0,
        tpsl='tp',
        is_market=True,
        reduce_only=True
    )
    print(f"TP Order Result: {result}")
except Exception as e:
    print(f"TP Order Error: {e}")
    import traceback
    traceback.print_exc()
