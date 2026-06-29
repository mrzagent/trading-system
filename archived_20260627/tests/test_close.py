import sys
sys.path.insert(0, r'D:\dev\trading')

from trade_executor import HyperliquidClient

client = HyperliquidClient()
positions = client.get_positions()
print(f"Found {len(positions)} positions:")
for p in positions:
    print(f"  {p['coin']}: {p['size']} @ ${p['entryPx']}")

# Try to close SOL
if positions:
    for p in positions:
        if p['coin'] == 'SOL':
            print(f"\nClosing SOL position...")
            try:
                result = client.close_position_market('SOL')
                print(f"Result: {result}")
            except Exception as e:
                print(f"Error: {e}")
