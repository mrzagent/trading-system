"""Check actual HyperLiquid positions"""
import sys
sys.path.insert(0, r'D:\dev\trading')

from trade_executor import TradeExecutor, RiskConfig
import os
from dotenv import load_dotenv
load_dotenv(os.path.expanduser('~/.openclaw/.env'))

print("Checking HyperLiquid positions...")
executor = TradeExecutor(RiskConfig())

try:
    positions = executor.get_positions()
    print(f"\nOpen positions on HyperLiquid: {len(positions)}")
    for pos in positions:
        print(f"  {pos['coin']}: {pos['side']} {pos['szi']} @ {pos['entryPx']}")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
