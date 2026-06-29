from trade_executor import TradeExecutor, RiskConfig
import json

# Load the config
with open('risk_config.json') as f:
    config = json.load(f)

risk = RiskConfig(**config)
print('='*60)
print('RISK CONFIGURATION')
print('='*60)
print(f"Initial Capital: ${risk.initial_capital:,.2f}")
print(f"Risk per Trade: {risk.risk_per_trade_pct*100:.1f}% (${risk.risk_per_trade:.2f})")
print(f"Max Position: {risk.max_position_pct*100:.0f}% of capital")
print(f"Max Open Positions: {risk.max_open_positions}")
print(f"Stop Loss: {risk.stop_loss_pct*100:.1f}%")
print(f"Leverage: {risk.leverage:.0f}x")
print()
print('TAKE PROFIT LEVELS (Partial Closes):')
print('-'*60)
for tp in risk.get_tp_levels():
    print(f"  {tp.label}: +{tp.level*100:.0f}% move | Close {tp.close_pct*100:.0f}% of position")
print()

# Simulate a trade
print('='*60)
print('SAMPLE TRADE SIMULATION: BTC Long @ $100,000')
print('='*60)
entry = 100000
sl = entry * (1 - risk.stop_loss_pct)
print(f"Entry: ${entry:,.2f}")
print(f"Stop Loss: ${sl:,.2f} (-{risk.stop_loss_pct*100:.1f}%)")
print()
print('Take Profit Targets:')
tps = risk.get_tp_levels()
for tp in tps:
    tp_price = entry * (1 + tp.level)
    print(f"  {tp.label}: ${tp_price:,.2f} (+{tp.level*100:.0f}%) -> Close {tp.close_pct*100:.0f}%")

# Position sizing
print()
print('POSITION SIZING (with 3x leverage):')
price_distance = entry - sl
position_value = (risk.risk_per_trade / risk.stop_loss_pct)
margin_required = position_value / risk.leverage
position_size = position_value / entry
print(f"  Risk Amount: ${risk.risk_per_trade:.2f}")
print(f"  Position Value (notional): ${position_value:,.2f}")
print(f"  Margin Required: ${margin_required:,.2f}")
print(f"  Position Size: {position_size:.6f} BTC")

# Partial close breakdown
print()
print('PARTIAL CLOSE BREAKDOWN:')
for i, tp in enumerate(tps):
    tp_price = entry * (1 + tp.level)
    close_value = position_value * tp.close_pct
    profit = (tp_price - entry) * (position_size * tp.close_pct)
    print(f"  {tp.label} @ ${tp_price:,.0f}: Close ${close_value:,.2f} worth (+${profit:.2f} PnL)")
    if i == 0:
        print(f"         -> After TP1: SL moves to breakeven (${entry:,.2f})")

print()
print('='*60)
print('TOTAL EXPOSURE: 4 TPs x 25% = 100% of position closed')
print('MAX RUNNER: If all TPs hit, final 25% runs to +20%')
print('='*60)
