#!/usr/bin/env python3
"""Fix ETH orders - cancel wrong order and place proper trigger orders"""
import sys
sys.path.insert(0, r'D:\dev\trading')

from trade_executor import HyperliquidClient, TradeExecutor, RiskConfig
import json

client = HyperliquidClient()

# Create executor to use cancel method
risk_config = RiskConfig(leverage=3.0, stop_loss_pct=0.05, take_profit_levels=[{"level": 0.03, "close_pct": 1.0}])
executor = TradeExecutor(risk_config)

# ETH position details
symbol = 'ETH'
sz = 0.0337
entry_price = 1569.1
sl_price = 1545.55  # 1.5% below entry
tp_price = 1616.15  # 3% above entry

print(f"ETH Position: LONG {sz} @ ${entry_price}")
print(f"Target SL: ${sl_price}")
print(f"Target TP: ${tp_price}")

# Get current orders
orders = client._exchange.info.open_orders(client.MAIN_WALLET)
eth_orders = [o for o in orders if o.get('coin') == symbol]

print(f"\nExisting ETH orders: {len(eth_orders)}")
for o in eth_orders:
    print(f"  OID {o.get('oid')}: {o.get('side')} @ ${o.get('limitPx')}")

# Cancel existing ETH orders using the executor's cancel method
if eth_orders:
    print(f"\nCancelling {len(eth_orders)} ETH order(s)...")
    for o in eth_orders:
        oid = int(o.get('oid'))
        try:
            result = client.cancel_order(symbol, oid)
            print(f"  Cancel OID {oid}: {result}")
        except Exception as e:
            print(f"  Cancel OID {oid} failed: {e}")

# Now place proper trigger orders
print("\nPlacing SL trigger order...")
try:
    result = client.place_trigger_order(
        coin=symbol,
        is_buy=False,
        sz=sz,
        trigger_px=sl_price,
        limit_px=sl_price,  # Market execution on trigger
        tpsl='sl',
        is_market=True,
        reduce_only=True
    )
    print(f"SL Response: {json.dumps(result, indent=2)}")
    sl_oid = None
    if result.get('status') == 'ok':
        statuses = result.get('response', {}).get('data', {}).get('statuses', [])
        if statuses and 'resting' in statuses[0]:
            sl_oid = statuses[0]['resting']['oid']
            print(f"SL Order ID: {sl_oid}")
        elif statuses and 'error' in statuses[0]:
            print(f"SL Error: {statuses[0]['error']}")
except Exception as e:
    print(f"SL Exception: {e}")

print("\nPlacing TP trigger order...")
try:
    result = client.place_trigger_order(
        coin=symbol,
        is_buy=False,
        sz=sz,
        trigger_px=tp_price,
        limit_px=tp_price,  # Market execution on trigger
        tpsl='tp',
        is_market=True,
        reduce_only=True
    )
    print(f"TP Response: {json.dumps(result, indent=2)}")
    tp_oid = None
    if result.get('status') == 'ok':
        statuses = result.get('response', {}).get('data', {}).get('statuses', [])
        if statuses and 'resting' in statuses[0]:
            tp_oid = statuses[0]['resting']['oid']
            print(f"TP Order ID: {tp_oid}")
        elif statuses and 'error' in statuses[0]:
            print(f"TP Error: {statuses[0]['error']}")
except Exception as e:
    print(f"TP Exception: {e}")

# Verify final state
print("\n=== Final ETH Orders ===")
orders = client._exchange.info.open_orders(client.MAIN_WALLET)
eth_orders = [o for o in orders if o.get('coin') == symbol]
for o in eth_orders:
    print(f"  OID {o.get('oid')}: {o.get('side')} @ ${o.get('limitPx')} (reduceOnly={o.get('reduceOnly')})")
